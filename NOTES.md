# Technical notes

Implementation-side findings for the Mario Kart DS Archipelago world - the "why" and "how
we know" behind `rom_addresses.py` and the rest of `worlds/mkds/`. `Instructions.txt` is
the design spec; `rom_addresses.py` is the authoritative source for every confirmed
address/offset (each entry there carries its own confidence level and verification method
in its comment). This file covers what those two don't: architecture context, design
decisions worth remembering, and methodology traps to avoid repeating.

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

**Item naming (cups/tracks/missions)**: each required cup, time-trial track, AND mission
gets its own individually-named item (e.g. "Mushroom Cup", not a generic "Progressive
Cup") - missions were a later addition to this pattern (see "One free unlock per
section" below), same reasoning applies unchanged. Position 0 in each category's
required sequence is always free (no item needed); every other position is gated on
*receiving that exact position's own item* - not a count, not a predecessor chain. This
preserves the same solvability guarantee the old count-based "Progressive Cup x N" design
had (a well-defined, always-solvable access hierarchy with a free entry point) while letting
the received item's name say what it actually unlocks. The old counted design's guarantee
was never stronger than this anyway - identical "Progressive Cup" copies could be placed by
the fill algorithm in any order, so "hold N copies" never actually enforced strict
sequential play.

**All 36 real karts are individually unlockable** (`items.KARTS`, wiki-cross-verified
against mkds-re's real `KartId` enum - see `rom_addresses.KART_ID_TO_NAME`), each usable
by any character (mkds-re confirms no engine-level kart/character pairing restriction).
Supersedes an earlier design that collapsed everything to a single shared "Standard
Kart" item - see "All 36 karts individually unlockable" below for the redesign and a
real fill-deadlock bug (pre-existing in that earlier design, not introduced by the
expansion) found along the way.

**Time Trial track access is derived entirely from Grand Prix cup-unlock state** (no
independent per-track flag) - not directly relevant anymore since access itself is no
longer restricted either way (see below); tracks stay individually-named items purely for
the goal-logic layer (`rules.py`), same pattern as cups.

**Missions are item-gated the same way cups/tracks are** (changed - see "One free unlock
per section" below; originally missions had no item at all, unconditionally reachable).
Randomize Mission Mode still only controls whether Mission Mode participates in the AP
economy at all - slot shuffling (which mission occupies which level position) was
dropped separately and stays dropped; only *access* changed, not vanilla slot placement.

**`create_regions` only instantiates goal-required locations**, not the full ~198-location
table - matches Instructions.txt's actual design (non-required content isn't a real AP
location at all, not just "doesn't need an item"). If this ever changes, remember
`create_items`'s pool sizing and `rules.py`'s rule-iteration both currently assume it.

## Check-validity enforcement (replaced the ASM-patch approach)

After the ASM-patch investigation below found no way to suppress vanilla's baseline
content (8 starters, base karts, 4 free cups - nothing gates them at the game level), the
design pivoted: force the game fully unlocked, and gate *checks* instead of *access*. A
check only sends if the character AND kart actually used for the run were legitimately
received as items - not just the cup/track/mission itself. This trades "physically
impossible to cheat" for "no incentive to cheat," which sidesteps the ASM problem
entirely rather than solving it.

**`_apply_received_items`** (`client.py`) no longer does incremental per-item bit-writes -
it just writes `UNLOCK_MASK_EVERYTHING` once, idempotently, completely decoupled from
`ctx.items_received`. The old per-character unlock-bit mapping (`CHARACTER_UNLOCK_BITS`
and its individual `UNLOCK_BIT_DAISY`/etc. constants) was removed from `rom_addresses.py`
entirely once nothing referenced it anymore (see "One free unlock per section" below -
`STARTER_CHARACTERS` went the same way). `CUP_UNLOCK_MASKS` is kept, still unused by any
code path, purely as historical documentation of the empirical bit map (the bits
themselves are still real and still what `UNLOCK_MASK_EVERYTHING` sets) - the individual
constants feeding it aren't reused anywhere else the way the character ones weren't.

**The bootstrap deadlock** (found via real testing, not anticipated in the initial
design): requiring the kart item on *every* location - including position 0, which
already needs no cup/track item as the fill algorithm's bootstrap - makes literally
nothing reachable with zero items, so the fill algorithm has nowhere to even place the
kart item itself. `FillError` on generation, not a subtle bug. Fixed by exempting
whichever location already serves as the zero-item bootstrap (position 0 of cups/tracks,
or the first required mission if neither is active) from the kart requirement too, rather
than introducing competing bootstrap rules. **This exemption has to match, exactly, in
two independent places**: `rules.py`'s access rules (logical reachability, checked at
generation time) and `client.py`'s live validity check (real-time, checked during actual
play) - if they disagree about which location is exempt, either the solver thinks
something is reachable that the client will never actually reward, or vice versa.
Rather than re-derive the same "which location is bootstrap" logic twice, `rules.py`
computes it once (`world.kart_bootstrap_exempt_locations`, populated in the same loop
that sets access rules) and `fill_slot_data()` exposes it directly - `client.py` never
recomputes it, just reads the list. General lesson: when a new cross-cutting requirement
gets layered onto existing per-category rules, check whether it breaks the "something is
always reachable with nothing" invariant before assuming the layering is safe.

### One free unlock per section (extended the position-0-is-free pattern everywhere)

Cups/tracks already had "position 0 is free, every other position needs its own item."
Characters and missions didn't - **all 8 starter characters were simultaneously usable
from the start** (a fixed `STARTER_CHARACTERS` set, unconditional), and **missions had no
item gate at all** (every required mission unconditionally reachable). Both now follow
the same pattern:

- **Characters**: expanded from 4 items (the "lockable" ones) to all 12
  (`items.CHARACTERS` is now `list(rom_addresses.CHARACTER_ID_TO_NAME.values())`, single
  source of truth). One random character is free per seed
  (`rules.choose_character_unlock_order`, exposed via slot_data as
  `character_unlock_order`) - `client.py`'s `_is_run_legitimate` checks against
  `character_unlock_order[0]` instead of the old fixed 8-name set. Characters still don't
  gate any location's reachability (no access rule needed in `rules.py` - unlike
  Standard Kart, "which character" never affects whether a cup/track/mission can be
  logically reached, only whether `client.py` honors the check it produces), so this
  can't be unit-tested via `assertBeatable` the way cups/tracks/missions can - only a
  pool-content assertion (`TestCharacterUnlockOrder`).
- **Missions**: now item-gated exactly like cups/tracks (`rules.py`'s `set_rules` gained
  a `" - Clear"` branch using the same `_sequence_access_rule`). This *simplified*
  `set_rules`, not just extended it: the old single shared "bootstrap location" special
  case (`has_cup_or_track_bootstrap`/`bootstrap_mission` - only exempt the first mission
  from the kart requirement if neither cups nor tracks were active) is gone entirely, since
  every active category now independently exempts its own position 0. Never fewer
  bootstrap points than before, so no risk of reintroducing the original deadlock.
- **Real bug fixed along the way**: the old character-legitimacy check never consulted
  `randomize_characters` at all - turning that option off never actually removed the
  character requirement, contradicting its own docstring ("off = no checks tied to
  them"). Fixed as part of the same rewrite (mirrors the `karts_active` on/off pattern
  the kart check already used correctly).
- **PopTracker pack** got a matching rework: Cups/Tracks/Missions became 3-stage
  `progressive` items (locked / unlocked-green / unlocked-completed-grey) instead of
  plain toggles, driven by two independent Lua signals (`AddItemHandler` for unlock,
  a new `AddLocationHandler` for completion) plus `Archipelago.CheckedLocations` to
  correctly resync completed items after a reconnect (bumped `min_poptracker_version` to
  0.25.2 for that API). **Found and fixed a real drift bug** in the process: the old
  `item_name_to_code.lua` was hand-maintained and kept tracks/missions' LOCATION name
  (e.g. `"... - Clear"`) as the lookup key, when the real AP item-received event fires
  with the bare item name - those two were never equal, so tracks/missions could never
  have shown as unlocked from a real item event. `generate_pack.py` (recreated - wasn't
  persisted on disk before this round) now derives every item/location code mapping
  directly from `worlds/mkds`'s own item/location tables, so this class of drift can't
  recur. Tabs (Characters/Cups/Time Trial/Missions) were also dropped in favor of one
  continuously-scrollable page, per direct request.

### All 36 karts individually unlockable (replaced the single "Standard Kart" item)

Follow-up request: "all karts should be unlockable, not just the standard kart" - only
the standard-tier kart (1 of 36 real karts) had ever been individually legitimizable;
the other 24 (2 per character) had no item at all and could never send a check no matter
what was received.

- **Real kart names, wiki-cross-verified**: `rom_addresses.KART_ID_TO_NAME` (36 entries)
  checked against TWO independent mariowiki.com pages (the "Mario Kart DS karts" category
  listing and a per-character breakdown) - both agree with each other and with mkds-re's
  `KartId` enum grouping/order, name-for-name. Two symbol-name quirks worth remembering:
  `KartId_LightTrippler`'s real name is "Light Tripper" (one fewer 'l'), and
  `KartId_ROBBLS`/`_ROBLGS` render with a hyphen in-game ("ROB-BLS"/"ROB-LGS").
  `is_standard_kart()`'s tier-only formula was removed - superseded by this full table.
- **First attempt (superseded): mandatory `has_any` progression items.** Mirrored cups/
  tracks/missions exactly - all 36 as `state.has_any(KARTS, player)`-gated Progression
  items, sized to fit available pool capacity (trimmed like Characters, but proven to
  always keep >= 1 whenever any goal category is active). This fixed a real capacity-
  overflow risk (36 mandatory items would never fit a goal needing only 1-2 locations)
  but NOT a deeper problem, described next.
- **The real bug: a provable fill deadlock, not just an overflow.** For a THIN category
  (missions/time trials - exactly 1 location per required instance, unlike cups' 4-track
  multiplier), the single always-free bootstrap location can only ever hold ONE of two
  simultaneously-needed items (a kart item and the category's own next item) - whichever
  one doesn't fit ends up needing itself to be reachable. Proven unsatisfiable for ANY
  fill order via a sphere argument: whichever item lands at the one free slot, sphere 1
  is empty regardless of which one it was, so nothing past it is ever reachable. This
  wasn't introduced by the 36-kart expansion - the original single "Standard Kart" item
  had the exact same shape (always exactly 1 mandatory kart item competing for the same
  slot) and would have hit `Fill.FillError` for any real `missions_count`/
  `time_trials_count` goal (count >= 2) combined with Randomize Karts. Nobody had tested
  that exact combination before -
  `test/__init__.py`'s `TestKartsWithThinCategoryNoLongerDeadlocks` is a direct
  regression test for it now.
- **Final design: Karts mirror Characters exactly.** Reclassified `useful`, not
  `progression` (this also un-does an old deliberate deviation from Instructions.txt's
  "Karts: Useful" - no longer needed). One random kart is free per seed by NAME only
  (`rules.choose_kart_unlock_order`, mirrors `choose_character_unlock_order`) - no item,
  no rules.py access-rule presence at all, checked client-side exactly like the free
  character. The other 35 are one-copy Useful items sharing ONE combined bonus-pool
  trim with Characters (`__init__.create_items()`), rather than two separate capacity
  computations. This removes karts from the access-rule graph entirely, which removes
  the deadlock at its root - simpler than the first attempt, not just safer.
  `kart_bootstrap_exempt_locations` (the location-based exemption this superseded) is
  gone; `client.py`'s `_is_run_legitimate` no longer takes a `location_name` parameter at
  all, since kart legitimacy is now purely name-based, same as character legitimacy.
- **PopTracker pack**: `images/kart.png` (already existed for the old single item) is
  reused for all 36 - simple two-state toggles, no location tracking, exactly like
  Characters (no completion concept). Own layout section (`layouts/karts`), 3-per-row
  grid grouped by character (matches `KART_ID_TO_NAME`'s own block-of-3 order). Also
  found and fixed a real bug in `generate_pack.py` itself while writing it: the
  generated Lua comment headers were missing their `--` prefix on continuation lines
  (the header string and the `_comment_header` helper both added it, meaning it appeared
  once from each and then, after the first fix pass, was missing entirely) - would have
  been invalid Lua syntax (a bare, non-commented text line). Caught by re-reading the
  generated files, not by any automated check - no Lua interpreter available in this
  environment (see the apworld-packaging methodology note elsewhere in this file).

**Not yet live-verified** (implemented from research/existing confirmed addresses, not
yet checked against real gameplay - flagged rather than assumed correct, matching this
project's established discipline): the `RaceConfig.racer_entries[player_driver_id].
character_id`/`.kart_id` reads specifically for the cup-win and mission-clear validity
checks (the underlying addresses/offsets are long-confirmed for other purposes, but this
exact read hasn't been cross-checked against what's on screen); Time Trial's finish-time
comparison, which needs `RaceStatus`'s `RaceTime` byte format decoded before it can
safely send a check (`client.py`'s `_decode_finish_time` deliberately returns `None` -
skip, never send - until that's confirmed, rather than guessing a layout that could
silently send a wrong result the way the old RaceConfig-offset saga did); and all 36
karts individually unlocking specifically (the underlying character_id/kart_id read is
long-confirmed, but the kart-name resolution and free-kart-by-name check built on top of
it are new).

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

## ASM patch investigation - superseded, kept for historical/technical reference

**Superseded by the check-validity enforcement design above** - the world no longer needs
or attempts to suppress vanilla's baseline access at all. Kept below because the technical
findings (toolchain locations, the confirmed `g_SaveDataHolder` pointer chain, the overlay
map, everything ruled out) are real, verified work that could still be useful if binary
patching is ever revisited for a different reason - not because this is still an open
problem blocking anything today.

**The original problem**: `UNLOCK_FLAGS_ADDRESS` (RAM-write enforcement) fully and reliably
controls the 9 things vanilla MKDS gates behind its own save flags (Star/Special/Leaf/
Lightning cups, Mirror Mode, Dry Bones, Daisy, Waluigi, R.O.B.). It does **not** control the
8 starter characters, each character's first 2 karts, or the 4 default-unlocked cups -
vanilla treats these as always-available with no flag anywhere gating them, so there was
nothing to write to restrict them. Suppressing this would have needed a binary ASM patch to
the ROM itself; investigated at length, not achieved, then the requirement itself was
designed around instead (see above).

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
