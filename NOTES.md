# Technical notes

Implementation-side findings for the Mario Kart DS Archipelago world - the "why" and "how
we know" behind `rom_addresses.py` and the rest of `worlds/mkds/`. `Instructions.txt` is
the design spec; `rom_addresses.py` is the authoritative source for every confirmed
address/offset (each entry there carries its own confidence level and verification method
in its comment). This file covers what those two don't: architecture context, design
decisions worth remembering, methodology traps to avoid repeating, and the current state of
the unresolved ASM-patch investigation.

This is a condensed, actively-maintained reference, not a session log - superseded findings
and resolved incidents have been cut. For the full chronological development history
(including abandoned mechanisms and the complete investigation trail), see
[`NOTES_ARCHIVE.md`](NOTES_ARCHIVE.md).

## Data sources and target ROM

- **Primary source: [github.com/XorTroll/mkds-re](https://github.com/XorTroll/mkds-re)**, a
  reverse-engineered decompile of the EU build - `re-export/include/mkds-eu-types.h` (struct
  layouts, exact field offsets) and `re-export/mkds-eu-symbols.x` (global addresses). Struct
  *layouts* are compiled-logic-derived and trustworthy; global *addresses* for actual
  variables/tables have been 100% reliable live; **function addresses have not** - see the
  ASM investigation section below.
- **Target ROM is EU (gamecode `AMCP`)**, not USA. Early development targeted USA with
  addresses empirically ported from mkds-re's EU values (guessed offsets, then live-tested) -
  that approach worked for some addresses (e.g. a flat `-0x20` shift for `g_GlobalMV`) but
  produced a genuinely unreliable result for `RaceConfigManager` (an empirical byte-offset
  from a different struct, which drifted under real play and once returned a
  wrong-but-plausible value matching an actual different track - confirmed live, not
  theoretical). Switched to EU once an EU ROM was available: every mkds-re address now works
  *directly*, no porting or guessing, and every single one has been immediately reliable in
  exactly the way the ported USA addresses were not. `validate_rom` requires `AMCP` exactly.
- Community cheat-code sources (gamemasterplc/codejunkies/neoseeker) only have broad
  "unlock everything" codes - no granular per-item codes exist anywhere; the full bit map in
  `rom_addresses.py` was derived from scratch (bisection testing on USA, carried over
  unchanged to EU since it's the same compiled logic at the same address).

## BizHawk client integration basics

- Memory domain for NDS/melonDS is **`"ARM9 System Bus"`** (confirmed via
  `pokemon_platinum.apworld`'s real, shipped source - a genuine BizHawk-via-NDS world,
  read directly rather than guessed). The raw cartridge header specifically needs the
  `"ROM"` domain instead - `"ARM9 System Bus"` doesn't reliably show it at a fixed address
  (can be shadowed by Instruction TCM remapping).
- Core calls: `bizhawk.read(ctx, [(address, length, domain)])`, `bizhawk.write`,
  `guarded_read`/`guarded_write` (guards against the target changing between read and write).
  A world's client subclasses `BizHawkClient`, implements `validate_rom`/`game_watcher`.
- `reference/ram_probe/probe.lua` is a standalone investigation tool (not shipped) - watches
  trigger files and performs reads/writes/scans/hardware-watchpoint registration on command,
  driven externally rather than clicked through by hand. See its own header comment for the
  full command reference (`READAT`, `FINDBYTES`, `SCANSTART`/`SCANDIFF`,
  `NARROWSTART`/`NARROWTOGGLE`/`NARROWDUMP`, `WATCHREAD`/`WATCHWRITE`/`WATCHEXEC`/`WATCHDUMP`/
  `WATCHCLEAR`, `PRESS`/`TOUCH`/`WAIT`/`REBOOT`/`SCREENSHOT`).
- `reference/asm_tools/` is a second, BizHawk-independent toolkit (pure Python, reads the ROM
  file directly) for static analysis: BLZ/LZ-Overlay decompression (`mkds_disasm.py`, a
  careful port of `Barubary/dsdecmp`'s reference implementation - the ARM9 binary and every
  overlay are compressed this way), NDS overlay-table/FAT parsing, resilient ARM/THUMB
  disassembly via `capstone`, and literal-pool cross-referencing (`find_literal_refs.py` -
  finds what code loads a given address as a PC-relative constant).

## Design decisions worth remembering

**Item naming (cups/tracks)**: each required cup and time-trial track gets its own
individually-named item (e.g. "Mushroom Cup", not a generic "Progressive Cup"). Position 0
in the required sequence is always free (no item needed); every other position is gated on
*receiving that exact position's own item* - not a count, not a predecessor chain. This
preserves the same solvability guarantee the old count-based "Progressive Cup x N" design
had (a well-defined, always-solvable access hierarchy with a free entry point) while letting
the received item's name say what it actually unlocks. The old counted design's guarantee
was never stronger than this anyway - identical "Progressive Cup" copies could be placed by
the fill algorithm in any order, so "hold N copies" never actually enforced strict
sequential play.

**Karts have no per-kart flag** (confirmed via mkds-re's `ExtraKartUnlockState`/
`CharacterKartUnlockFlags` enums - authoritative, matches earlier empirical testing where
unlocking characters cascaded into "all karts unlocked"). Availability is a coarse 4-tier
progress state, not an individual flag, so kart randomization works by patching each
character's *starting kart assignment* rather than hooking a native per-kart unlock. "Yes
only each character's unique karts" is fully achievable by forcing the existing tier to
`TotalUnlock` - vanilla's own per-character picker does the rest correctly. "Yes all" (any
character, any unlocked kart) has no vanilla UI path at all and is an **open design fork**:
either an ASM patch to the kart-select bounds-check (candidate:
`CheckExtraKartUnlockFlagsWith`, EU `0x02056DAC`), or writing the intended kart directly into
`RaceConfig.racer_entries[player_driver_id].kart_id` before the race starts - which still
needs some UI for the player to express which received kart they want, since vanilla's
picker can't browse all 36. Not implemented either way; worth the user's input when this
becomes the active blocker.

**Time Trial track access has the same shape of problem**: derived entirely from Grand Prix
cup-unlock state (win a cup, its 4 tracks become time-trial-selectable) - no independent
per-track flag exists. `items.py` has one item per track (32 total, per Instructions.txt),
but the native mechanism only unlocks in groups of 4. Not blocking anything built so far
(`rules.py`'s logic layer doesn't care how the real unlock eventually gets implemented), but
whoever implements the real client-side enforcement needs either an ASM patch or a different
granularity decision.

**Missions have no "Progressive Mission" item** - Randomize Mission Mode only shuffles which
mission occupies each of the 63 slots, it doesn't gate access to Mission Mode itself. Mission
locations use an unconditional access rule regardless of required-ness.

**`create_regions` only instantiates goal-required locations**, not the full ~198-location
table - matches Instructions.txt's actual design (non-required content isn't a real AP
location at all, not just "doesn't need an item"). If this ever changes, remember
`create_items`'s pool sizing and `rules.py`'s rule-iteration both currently assume it.

## Methodology lessons (things that cost real time once - avoid repeating)

- **`client.reboot_core()` reloads RAM from the last *saved* `.sav` state, not live RAM** -
  it silently discards any not-yet-saved write. Never reboot between a write-test and its
  verification unless the write is also meant to survive a save reload; use a menu
  back-out/back-in to force a screen reread instead. A reboot-based "refutation" of an
  otherwise-sound hypothesis deserves a no-reboot retest before being trusted.
- **A direct memory poke (`memory.write_bytes_as_array` / BizHawk's write API) does not
  trigger CPU-bus hardware watchpoints** - only genuine `STR`/`LDR` instructions executed by
  the emulated CPU do. This isn't a bug, just a real distinction between "poke a value" and
  "the game's own code touches this address."
- **Never register a wildcard `WATCHREAD`/`WATCHWRITE`/`WATCHEXEC` (`ANY`, no address
  filter)** except the briefest deliberate test. It fires on every matching bus operation
  system-wide and the per-call Lua overhead can't keep up - this hard-crashed BizHawk once.
  Prefer a specific address; `probe.lua`'s `WATCHEXEC` deliberately doesn't even accept `ANY`.
- **Two internally-consistent-looking live samples are not sufficient cross-validation** for
  an empirically-derived address/offset (as opposed to a real static pointer). The failure
  mode that bit this project (landing on an inactive-but-structurally-plausible copy of a
  struct, e.g. `RaceConfigManager.next_race` instead of `.cur_race`) produces results that
  look locally consistent on their own. Real cross-validation needs either enough
  independent samples that coincidence becomes implausible, or a field whose correctness
  can't be faked by chance.
- **mkds-re's data symbols (globals, struct field offsets) have been 100% reliable under live
  testing; its function symbols have not been independently verified even once**, and two
  separate ones failed close inspection (see the ASM section below - one disassembles to an
  unrelated function when the real prologue is found a few bytes earlier; another's address
  contains a bare `BX LR` in ARM mode and garbage in THUMB mode despite real call sites
  targeting it). Don't build on a function address without live verification (e.g.
  `WATCHEXEC`) - trust data/struct addresses freely, don't trust function addresses blindly.
- **AP's `WorldTestBase` subclasses need a truthy `options = {...}` (or an overridden
  `setUp`/`world_setup`)** - without one, every inherited test (`test_fill`,
  `test_all_state_can_reach_everything`, etc.) silently no-ops rather than failing. A test
  suite that "passes" may not have exercised real generation at all; verify by checking it
  actually catches a deliberately-introduced break, not just that it's green.
- **Lua's `a and b or c` is not a safe ternary** when `b` can be `nil`/`false` - it silently
  falls through to `c` regardless of `a`. Use an explicit `if/then` assignment instead.
- When testing which BizHawk input (`PRESS` vs `TOUCH`) a given screen needs, don't assume -
  MKDS's title/mode-select screens are touch-only, cup/character/kart select are
  button-driven, and this isn't visually obvious from a screenshot alone.

## ASM patch investigation - paused, documented as a known limitation

**The problem**: `UNLOCK_FLAGS_ADDRESS` (RAM-write enforcement) fully and reliably controls
the 9 things vanilla MKDS gates behind its own save flags (Star/Special/Leaf/Lightning cups,
Mirror Mode, Dry Bones, Daisy, Waluigi, R.O.B.). It does **not** control the 8 starter
characters, each character's first 2 karts, or the 4 default-unlocked cups - vanilla treats
these as always-available with no flag anywhere gating them, so there is nothing for this
world to write to restrict them. Suppressing this would need a binary ASM patch to the ROM
itself. Investigated at length; not yet achieved. Documented in `docs/setup_en.md` and the
README as a known limitation rather than continuing to chase it unboundedly.

**Toolchain** (if resumed): `devkitARM` (real, complete - `F:\devkitPro\devkitARM\bin\`,
`arm-none-eabi-gcc` 16.1.0 + linker/objcopy/etc.) and `Fireflower` (real, complete -
`F:\fireflower\`, `nds-build.exe`/`nds-extract.exe` for ROM pack/unpack) are both confirmed
present and working. `NCPatcher` (what mkds-re's own `asmhack-examples` use) is **not**
installed and would need bootstrapping `cmake` from source first - decided to skip it
entirely and drive `arm-none-eabi-gcc`/`ld`/`objcopy` + Fireflower directly via custom Python
tooling instead, avoiding the cmake-bootstrap detour and an unfamiliar tool's expected
project layout.

**Confirmed live**: `g_SaveDataHolder` (EU `0x0217AA08`, a static pointer) dereferences to a
heap-allocated struct; `UNLOCK_FLAGS_ADDRESS` sits at exactly that struct's base **+ 0x70**
(read `g_SaveDataHolder`'s value directly and did the arithmetic - not inferred from a side
effect). The struct mkds-re documents at that base (`SaveDataHolder`, 0x48 bytes) doesn't
account for reaching all the way to +0x70 on its own - the flags word is not simply
`SaveDataHolder`'s own field the way its `unk_bits`/`other_secret_bits` fields at +0x30/+0x34
might suggest; not resolved which allocation it actually belongs to.

**Overlay map** (ARM9 overlays 0-3, the dynamically-loaded menu/scene code regions):
- Overlay 0 and overlay 1 share the same RAM address (mutually exclusive, loaded at
  different times). **Overlay 1 is confirmed the real local-menu/select-screen overlay**
  (via embedded asset strings - `select_cup_course_ta_m.bncl`, `select_engine_m.bncl`, etc:
  cup/course select, time trial ghost select, class/battle-stage/option select). **Overlay 0
  is Nintendo WFC/GameSpy connection-flow code** (`gs.nintendowifi.net`, `GPI_NOT_CONNECTED`,
  SSL root CA strings) - unrelated to local menus.
- Overlay 2 is tiny (0x20 bytes) and uncharacterized.
- Overlay 3 is the **Wi-Fi hardware setup wizard** (`DWCi_MOV_WH_SYSSTATE_*`, `ESSID-AOSS`,
  WEP/IP/DNS keyboard-entry screen assets) - also unrelated to local menus.

**Ruled out** (multiple independent techniques, summarized - see git history for the
blow-by-blow if ever needed):
- Static function-call scanning found only 10 real call sites across the whole ROM to one
  named "check flag" function, all passing bit-indices matching the already-known Lightning
  Cup (12) and Mirror Mode (16) bits - nothing for the other 7 lockable bits, and nothing
  resembling a grid-population loop, in any of the 4 overlays or the main ARM9 binary.
- Literal-pool cross-referencing (every place code loads `g_SaveDataHolder`'s address as a
  constant) found ~24 real sites, almost all a "wait for save data ready" busy-check
  (`+0x28`) unrelated to unlocking; a promising-looking bit-manipulation cluster at
  `sv_header+0x31` turned out to be a "needs saving" dirty-flag byte
  (`WriteSaveDataSectionHeaderToSaveData_from_thumb` is called right after every hit).
  **None of these sites touch the `+0x70` unlock-flags offset.**
- Live hardware watchpoints (`WATCHREAD`) on both `g_SaveDataHolder`'s address and
  `UNLOCK_FLAGS_ADDRESS` itself: **zero hits**, even walking through an entire real
  navigation into Character Select while its on-screen content visibly depended on that
  data. Ruled out the mundane explanations first (watchpoint registration genuinely works -
  confirmed via a known-good call site and via `WATCHEXEC` working correctly elsewhere;
  `EnableJIT` confirmed off, since registration would otherwise throw). Leading theory: some
  fast-path (e.g. Data TCM) serves reads to this region in a way the "ARM9 System Bus"
  callback scope can't observe - not proven, but well-supported by elimination.
- `WATCHEXEC` (execution watchpoints, added specifically for this - unlike the read/write
  watches, these work correctly) on 23 real, independently-verified candidate addresses -
  the 2 named "secret flag" functions from mkds-re's symbol table, plus all 21 literal-pool
  cross-reference sites within overlay 1 - through a fresh Character Select load: **zero
  hits on all 23**. This is what surfaced the function-symbol reliability concern above.
- Two data-table leads (a clean sequential bitmask table matching 8 of the known unlock bits
  in overlay 3; a partial match in overlay 0) both refuted once those overlays' actual
  purpose (WFC/GameSpy, not menus) was checked via string search - false positives.
- Re-ran the same "sequential bitmask table" search constrained to overlay 1 specifically
  (the *confirmed* select-screen overlay): **zero matches**. If a simple index->bitmask
  lookup table exists for character/cup unlocking, it isn't sitting in the overlay
  responsible for that UI.

**Where this leaves it**: the elimination has been thorough enough to be confident the logic
is *not* a tidy shared table plus a shared check function reachable by any technique tried -
more likely inline and scattered per-character through a larger population routine, which
none of the current tooling is well-suited to locate. `reference/asm_tools/` has the full
reusable pipeline (decompression, overlay extraction, disassembly, literal-pool
cross-referencing, table search) ready for whoever picks this back up; the concrete
next-step idea nobody's tried yet is manually, systematically disassembling overlay 1 in
full rather than continuing to search for known patterns.
