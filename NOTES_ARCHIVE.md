# Technical notes / findings (ARCHIVE - full chronological history)

**This is the full, unedited session-by-session development log, kept for historical
detail (superseded addresses/mechanisms, the complete investigation trail, resolved
incidents).** For the current, actively-maintained reference - confirmed facts, design
decisions, methodology lessons, and the ASM-patch investigation's present state - see
[`NOTES.md`](NOTES.md) instead. This file is not maintained going forward.

---

Working notes from the build session on 2026-08-04. Instructions.txt is still the
authoritative design spec - this file is implementation-side findings that inform how
that spec gets built, not a restatement of it.

## Environment (confirmed present, 2026-08-04)
- BizHawk 2.9.1, 2.10, and 2.11 all installed under `G:\Archipelago\BizHawk-*-win-x64\`.
  TODO: figure out which version the frozen `ArchipelagoBizHawkClient.exe` expects.
- Frozen Archipelago distribution at `G:\Archipelago` (launcher, generator, server,
  clients, `custom_worlds\` for .apworld packages). This is where the finished
  `.apworld` will get dropped and tested.
- ROM confirmed at `E:\DS\Mario Kart DS (USA) (En,Fr,De,Es,It).nds`.
- The 100% save mentioned earlier in the project is not currently present at
  `G:\Downloads\mariokart_ds_100\...` - not blocking, the design starts from a fresh
  save regardless.
- `F:\Mario Kart DS AP\reference\Archipelago\` is a shallow clone of the AP source repo,
  kept only as a local reference for the World API / BizHawk client API / docs. It is
  NOT part of what ships.

## BizHawk client API (from reference/Archipelago/worlds/_bizhawk/README.md)
- The client talks to a Lua connector (`data/lua/connector_bizhawk_generic.lua`) over a
  socket. Core calls: `bizhawk.read(ctx, [(address, length, domain)])`, `bizhawk.write`,
  `guarded_read`/`guarded_write` (guard against an address's contents changing between
  read and write - important since a frame can pass in between), `lock`/`unlock`
  (discouraged - causes visible stutter).
- A world's client subclasses `BizHawkClient`, implements `validate_rom` and
  `game_watcher`, and sets `system`/`game` class vars.

## Confirmed via pokemon_platinum.apworld (real, shipped NDS-via-BizHawk world already
## installed in custom_worlds - extracted and read directly, not guessed)
- The correct BizHawk memory domain name for NDS/melonDS is **"ARM9 System Bus"**.
- Their pattern: read a *fixed* pointer address to find a dynamically-allocated custom
  struct, then verify it against a 16-byte header/signature via `guarded_read` before
  trusting it. This is more robust than trusting a raw hardcoded heap address outright -
  worth doing something similar for MKDS instead of leaning entirely on the
  community-documented 0x023CE2E0 address.
- Their `rom.py` (and pokemon_rb's `basepatch_*.bsdiff4`) implies real BizHawk worlds
  often ship a small ROM patch that injects a custom "AP struct" for bookkeeping
  (received-items queue, etc.) rather than only reading/writing the game's own native
  save structures. Open question below on whether MKDS needs this too.

## MKDS memory (community research - NOT yet verified against this exact ROM/BizHawk build)
- ARM9 code: ~0x02000000-0x02180000. Overlay code: ~0x02180000-0x021C0000.
  Heap: ~0x021DA340-0x023E0000.
- Candidate master unlock-flags structure: `0x023CE2E0`
  (https://xortroll.github.io/posts/mkds-mem-cheats/), claimed deterministic due to a
  consistent early heap-allocation order. A single write of `0x07FFFFFF` there reportedly
  unlocks everything (characters, karts, cups, classes, missions) at once, implying it's
  a bitfield spanning all of them - but no source found documents the individual
  bit-to-item mapping. That has to be derived empirically (see probe.lua below).
- Checked gamemasterplc / codejunkies / neoseeker cheat-code listings directly: they only
  have broad "unlock everything" style codes, no granular per-character/per-kart codes.
  No shortcut available there - confirmed, not just assumed.

## Existing manual_mariokartds_xanderoni.apworld (in custom_worlds - third-party,
## NOT the basis for this project, kept only as a cross-check)
- A Manual-framework world by a creator called "Xanderoni", unrelated to Instructions.txt
  (different filler item name "Coins" vs "Green Flag", includes Battle Mode which
  Instructions.txt never mentions, no automatic memory reading at all - confirmed via
  grep, zero bizhawk/memory references anywhere in its client).
- Mostly unfinished template scaffolding (`meta.json` and `docs/setup_en.md` are
  untouched boilerplate; its custom `hooks/Options.py` defines an example option that's
  never actually wired in).
- Still useful as a secondary data source: its character roster (12) and kart name list
  (24 unlockable karts) both check out against what I independently know of MKDS, so
  `items.py`'s `CHARACTERS`/`KARTS` lists were cross-checked against it. Its data also
  implies 7 Mission Mode levels (a "Progressive Mission Mode Level Access" item with
  count 7) - a useful data point, but not confirmation of the full mission structure.

## Open technical decisions (not yet made)
- Read/write the game's native unlock-flags struct directly, vs. inject a small custom
  ROM patch with our own AP-bookkeeping struct (like pokemon_rb/pokemon_platinum do).
  The latter is more robust but is real extra work (binary/ASM patching).
- Exact granularity of "Time Trials: Progressive" - `items.py` currently assumes one
  item per course (32 total) as a placeholder; Instructions.txt doesn't specify this.
- `items.py`/`locations.py` base IDs are arbitrary placeholders, not checked against the
  ~90 other apworlds already in `G:\Archipelago\custom_worlds` for collisions.
- The real 32-track roster (names + vanilla cup groupings) and the real Mission Mode
  roster (mission count per level, which are boss missions) are NOT filled in yet -
  `locations.py` uses clearly-marked placeholder names for both rather than asserting
  specifics that were never verified.

## RAM-mapping plan
`reference/ram_probe/probe.lua` watches a trigger file and dumps a labeled memory
snapshot on demand - meant to run in BizHawk while someone plays through specific
moments (character select, unlocking things, race finishes, mission clears/3-stars) so
before/after snapshots can be diffed to find real addresses.

### First live probe (2026-08-04)
BizHawk 2.11 launched with the ROM + probe.lua via `Start-Process ... EmuHawk.exe "<rom>" --lua="probe.lua"`. Confirmed working:
- `memory.getmemorydomainlist()` and `memory.read_bytes_as_array(addr, len, domain)` both work as expected in this BizHawk build.
- `memory.getmemorydomainsize("ARM9 System Bus")` reported 0 at script-load time (before the ROM had finished booting) - a red herring, not a real problem. Reads still succeeded fine once the game was actually running.
- Domain list for this core: Shared WRAM, ARM7 WRAM, SRAM, ROM, Instruction TCM, Data TCM, ARM9 BIOS, ARM7 BIOS, Firmware, **ARM9 System Bus**, ARM7 System Bus, Waterbox PageData.

Took a snapshot (label `initial_test`) of 0x023CE000-0x023CE7FF (2KB) while MKDS was running (exact screen unconfirmed - likely title/main menu, need to pin down). Findings:
- The region is NOT blank/uninitialized - it contains real, structured data, confirming reads are hitting live game memory correctly.
- Bytes 0x023CE000-0x023CE08F form a clear repeating 0x30-byte record pattern (3 records seen, then it changes shape at the 4th) with an incrementing ID field and what looks like `id*3` in another field - looks like some kind of active object/resource table, NOT obviously the unlock-flags bitfield. Not yet identified what this table actually is.
- The community-documented address `0x023CE2E0` itself read as `00 00 00 00` in this snapshot, with `0x00001388` (5000 decimal) immediately after it - does not look like the "all bits set" unlock-flags pattern the cheat code implies. Most likely explanation: we weren't at the right game state yet for that struct to be meaningfully populated (or allocated at all) - the xor.dev writeup's claim of a deterministic address may only hold from a specific point in the boot sequence onward. Need to re-check once at a known, specific screen (e.g. the mode-select or character-select screen) rather than whatever screen we happened to be on for this first test.

Next: pin down exactly what screen/state each snapshot corresponds to before drawing conclusions from byte diffs.

### Address 0x023CE2E0 confirmed real (2026-08-04, live test)
Extended probe.lua with a write trigger (write_trigger.txt, format "<hex addr> <hex byte> <hex byte> ...", writes to the same "ARM9 System Bus" domain). Live-tested against a running game on the character-select screen (Single Player > Grand Prix > 150cc):

- Wrote `07 FF FF FF` (LE for 0x07FFFFFF, the community "unlock everything" value) to `0x023CE2E0`. No visible change while still sitting on the screen - confirmed this struct is only read/applied when the screen *loads*, not live. Backing out and back into character select afterward: **everything was unlocked** (all characters selectable, Mirror Mode appeared on the CC select screen). This confirms the address and value are real and correct, at least for characters + Mirror Mode (probably cups/classes too per the original cheat description, not yet directly observed).
- Wrote `00 00 00 00` back (matches the value seen in the very first two snapshots, taken before any writes, at title screen and at a clean character-select visit) and reloaded the menu expecting a clean revert. Instead got a **visibly corrupted** character select screen (screenshot: `pictures/Character Select Screen Bug.PNG`): Bowser and Donkey Kong missing from the grid entirely; Dry Bones, Wario, and Waluigi all overlapping in a single grid slot.
- Interpretation: writing this one flags word alone is not sufficient to fully control/reset what gets displayed. There is very likely a second, derived structure elsewhere (e.g. a computed "which character goes in which grid slot" list) that gets built once and does not automatically get rebuilt just from changing this flag word back - so the flag and that cached layout went out of sync. The 0x00000000 value being "correct" for a fresh title-screen read but *not* safely restorable mid-session (after other state has been touched) is a real methodology hazard: testing by writing extreme values (all-set / all-clear) at arbitrary points in a play session can desync other cached state in ways that a simple bit-level read of this one address won't explain.

**Methodology change going forward**: prefer a full ROM reset/reboot (not just backing out of a menu) between write experiments to guarantee a clean slate, and prefer testing one bit at a time relative to a freshly-confirmed-clean baseline rather than jumping to extremes (all-set / all-clear). Also: unclear yet whether this address is written back to the .sav file at any point (e.g. on returning to the main menu) - worth avoiding letting the game autosave while in a deliberately-corrupted state. Confirmed this session is on a fresh/disposable save (user-confirmed), so low-stakes either way.

**Reset method matters a lot.** BizHawk's plain Reset (soft reset / console reset button equivalent) was NOT sufficient to clear the cached-state desync - confirmed by a case where the raw flag at 0x023CE2E0 read back as a clean 0x00000000 but the screen still showed "every character but Yoshi" (neither the clean baseline nor a coherent test result). BizHawk's **"Reboot Core"** (fully reinitializes the core, not just an in-console reset) reliably reproduces the clean 8-starters baseline. Use Reboot Core before every write test from here on, not plain Reset.

### Bit bisection results so far (all from a Reboot Core clean baseline: 8 starters, no bonus chars, no bonus cups)
- Bits 0-13 (`0x00003FFF`): no visible change on the character select screen. NOTE: character screen only was checked - cup/kart screens were NOT checked for this test, so this result is incomplete, not a clean "no effect" verdict. Revisit.
- Bits 14-26 (`0x07FFC000`): same visual corruption/glitch as the earlier all-zero-after-everything test on the character grid (missing/overlapping portraits) - BUT functionally all 12 characters were selectable despite the glitch. Also: **all karts became unlocked**, and **Lightning Cup specifically unlocked** (other locked cups did not). Likely conclusions: (a) kart availability may not be independently gated at all in vanilla MKDS - probably just follows character unlock automatically, worth keeping in mind for how Randomize Karts gets implemented later; (b) cup unlock bits are likely NOT all within 14-26 - Lightning Cup's bit is in there, but the others (Star/Special/Shell/Banana/Leaf presumably) are probably elsewhere, possibly in 0-13 (untested for cups) or outside this whole word entirely.
- The recurring visual corruption when jumping from 8->12 characters in one step (even from a clean reboot) may just be a rendering artifact of an abrupt, non-progressive change that real gradual gameplay unlocking would never trigger - not necessarily a sign of test invalidity. Worth keeping in mind rather than assuming every glitchy screen means the underlying flags are wrong.

**Process fix**: check the character select, kart select, AND cup select screens on every test from now on, not just whichever screen prompted the question - underclaimed "no change" results earlier were likely incomplete rather than accurate.

### Full clean baseline (Reboot Core, fresh save, confirmed 2026-08-04)
- Characters: 8 starters only (Mario, Luigi, Peach, Yoshi, Toad, DK, Wario, Bowser).
- Mario's default karts: **"B Dasher" and "Standard MR"**. Only 2 by default, not 3.
  IMPORTANT: "B Dasher" was in items.py's KARTS list (sourced from
  manual_mariokartds_xanderoni's "unlockable karts" data) - that source is now confirmed
  wrong on at least this one kart. Don't trust that list's locked/unlocked categorization
  further; items.py's kart list needs to be rebuilt from real observation, not that source.
  "Standard MR" isn't in items.py's KARTS list at all yet - needs adding once the real
  full kart roster (default + unlockable, per character) is mapped.
- Cups unlocked by default: **Mushroom, Flower, Shell, Banana**. Locked by default: Star,
  Special, Leaf, Lightning (4 locked cups - not a clean nitro-vs-retro split, it's a mix).
- Mirror Mode: locked by default (expected).
- Open architectural question raised by the bits-14-26 test: karts may not be
  independently flagged at all in vanilla MKDS - unlocking all characters also unlocked
  all karts in that test. If kart availability just cascades from character unlocks with
  no separate native flag, "Randomize Karts" as its own independent AP category may need
  custom logic/patching rather than a native flag to hook into. Not confirmed yet, but
  worth keeping in mind while continuing the bit mapping.

**Design decision (user, 2026-08-04)**: since kart availability doesn't look independently
flag-gated, our implementation will randomize which kart occupies each character's
*starting* kart slot (e.g. Mario might start with a different kart than vanilla's "B
Dasher"), rather than depending on a native per-kart unlock flag. This also explains why
manual_mariokartds_xanderoni's data listed "B Dasher" as an unlockable item - Manual
worlds are played on an already-100%-unlocked save with purely player-honor-system
tracking, so they don't need to reflect real in-game unlock mechanics at all. That
source's item categorization should not be trusted as a locked/unlocked signal - fine as
a name/existence reference only. TODO: fold this into Instructions.txt once the technical
picture is fuller - holding off on editing the spec mid-investigation.

### Bits 14-20 (0x001FC000) isolated from a clean baseline
Result: **Dry Bones** unlocked (only Dry Bones, not Waluigi or R.O.B.), **Mirror Mode**
unlocked, **Lightning Cup** unlocked, all karts unlocked again. So this 7-bit range
contains at least 3 distinct single-purpose bits (Dry Bones, Mirror, Lightning) plus
whatever triggers the karts cascade. Waluigi and R.O.B. must be in bits 21-26 (the other
half of the original 14-26 split) since they weren't unlocked here but were in the wider
14-26 test.

Also notable: Leaf Cup has not unlocked in ANY test so far (baseline-locked cups were
Star, Special, Leaf, Lightning; only Lightning has appeared). Its bit is likely NOT in
14-26 at all - probably in 0-13, which was only checked against the character screen
originally (see process fix above) - needs a proper retest with all three screens.

### Automation breakthrough (2026-08-04)
Extended probe.lua with scripted input (PRESS/TOUCH/WAIT/REBOOT) and client.screenshot(),
which I can read directly - no more relying on the user's text descriptions for
verification. Key findings from building this:
- `client.reboot_core()` works and the Lua script survives it fine, no reload needed.
- The main title menu is **touch-driven**, not button-driven - "Single Player" etc. are
  tap targets, not a cursor list. CC-select and character-select ARE button/cursor driven
  (A/Down work normally there). Kart select's "OK" confirm button appears to be touch-only
  again (button presses didn't advance past it in testing) - exact coordinates not yet
  nailed down reliably, ended up asking the user for that one hop rather than keep
  guessing blindly.
- **The attract-mode demo video starts ~7-8 seconds after landing on the title menu** with
  no input. This was silently corrupting earlier automation attempts (touches landing
  mid-video, or during the boot/logo sequence if fired too soon after reboot with too
  short a wait). Any future full-automation attempt needs to either act well within that
  window or chain a "dismiss" input first.
- Confirmed GP flow: title (touch) -> Grand Prix (A) -> CC select (Down/Down/A for 150cc)
  -> Character select (A) -> Kart select (touch OK, coords TBD) -> Cup select. B backs up
  one step at a time through this same chain.
- Current working model: I drive memory read/write and screenshot verification myself:
  the user only needs to help with menu navigation, which is faster and more reliable by
  hand than continuing to guess touch coordinates.

### Bits 21-26 (0x07E00000) isolated
Result: **Daisy, Waluigi, and R.O.B. all unlocked** (Dry Bones still absent - stays
isolated to 17-20). Kart select still showed only the default 2 karts for Mario - **no
kart cascade this time**, unlike the wider 14-26 and 14-20 tests. This narrows the "all
karts unlocked" side effect down to something specifically in 17-20 (most likely tied to
Dry Bones' own bit, not a general "any character unlocked" rule - not confirmed which
specifically, low priority to chase further right now). Cup select: **no additional cups**
- still just Mushroom/Flower/Shell/Banana, Star/Special/Leaf/Lightning all still locked.
So Star, Special, and Leaf's bits are NOT anywhere in 14-26 - almost certainly in 0-13,
which still needs a proper retest checking the cup screen (the original 0-13 test only
checked characters).

### Bonus: real Mushroom Cup track list confirmed via screenshot
Figure-8 Circuit, Yoshi Falls, Cheep Cheep Beach, Luigi's Mansion. Real data to replace
the TRACKS placeholder in locations.py once the full 32-track roster is gathered this way.

### User handed off for the night (2026-08-04, ~03:15)
User went to bed and explicitly authorized continuing autonomously using the ~7-8s
post-reboot title-menu timing they measured. Working solo from here using screenshot
self-verification. Constraint: probe.lua can no longer be edited+reloaded without the
user physically doing Lua Console > Open Script - so no more new macro commands or bug
fixes are possible this session. Working within the currently-loaded command set
(PRESS/TOUCH/WAIT/REBOOT/SCREENSHOT, plus the read/write triggers).

Kart-select's "OK" confirm button (advancing to Cup Select) has resisted several
different touch coordinate guesses - all either did nothing or bounced backward to
Character Select instead of advancing. Given I can't fix/inspect the script further
without the user, I'm not going to keep burning attempts on this - reliable navigation
right now is limited to: title (touch, ~x=128,y=20) -> Grand Prix (A) -> 150cc
(Down,Down,A) -> Character select (A) -> Kart select. B reliably goes back one step at a
time from anywhere in this chain. That's enough to fully automate character-bit testing
via reboot cycles; cup-bit testing beyond what's already found is on hold until the OK
button coordinate is sorted out (or another route to Cup Select is found - e.g. Time
Trial mode's course select might not require the same touch confirm, untested).

Bits 0-6 (0x0000007F) result (observed opportunistically, not a full clean test cycle):
character select showed the plain 8-starter baseline, no bonus characters. So bits 0-6
contain no character bits - consistent with the hypothesis that 0-13 is purely
cup-related (Star/Special/Leaf almost certainly live there, unconfirmed which exact bits
pending cup-screen access).

### Current isolation state
- Bits 0-13: unknown for cups/karts (only characters checked, incompletely - "no change"
  needs re-verification). Almost certainly contains Star Cup, Special Cup, Leaf Cup bits.
- Bits 14: no effect alone (likely unused/reserved).
- Bits 15+16 together: Mirror Mode. Bit 15 alone: nothing. Bit 16 alone: not yet tested.
- Bits 14+16 (via 14+15+16 minus a clean 15-alone result): Lightning Cup needs bit 14
  AND bit 16 together (not independent) - not a simple bitfield in this sub-range.
- Bits 17-20: Dry Bones, and probably the "unlock all karts" side effect.
- Bits 21-26: Daisy, Waluigi, R.O.B. (likely 3 of these 6 bits do the work, other 3 unused
  or something else not yet observed).

---

## Code implementation session, 2026-08-04 (later same day)

Wrote real apworld source at `F:\Mario Kart DS AP\worlds\mkds\`: `rom_addresses.py` (the
confirmed bit map as actual code constants), updated `items.py` (added "Standard MR",
corrected the B Dasher note), `regions.py`, `rules.py` (goal-scoping structure), `client.py`
(BizHawkClient skeleton), `__init__.py` (World class wiring). All cross-checked against
real reference code (pokemon_platinum.apworld, extracted and read directly) for exact API
shapes rather than guessed - e.g. `Location(player, name, address, parent)`,
`Region(name, player, multiworld)` + `region.connect()`, `set_rule`/`completion_condition`
from `worlds.generic.Rules`.

**Real validation, not just syntax checking**: installed the lightweight pure-Python deps
(`pathspec`, `schema`) needed for `BaseClasses`/`Options` to import, copied the world into
`reference/Archipelago/worlds/mkds/` (a test copy - source of truth stays
`F:\Mario Kart DS AP\worlds\mkds\`, re-sync before re-testing), and confirmed via
`worlds.AutoWorld.AutoWorldRegister` that our world **registers successfully as "Mario Kart
DS"** with zero load errors, alongside the ~15 other worlds that failed only because their
own heavier dependencies (bsdiff4, orjson, requests, etc.) aren't installed - AP's world
loader is resilient to individual world failures, confirmed. This means our class
definitions, imports, and framework wiring are structurally correct against the real API,
not just plausible-looking.

**Track/kart data completed via web research (2026-08-04)**: all 32 tracks and their cup
groupings (Special Cup's 4th is Rainbow Road - one search result had cut it off at 3),
and the full 36-kart roster organized by character (`items.py`'s `KARTS_BY_CHARACTER`).
Retro tracks got an SNES/N64/GBA/GCN system prefix to disambiguate real name collisions
(there's both a GBA "Luigi Circuit" and a separate GCN "Luigi Circuit", for instance).
Only Mario's default-vs-unlockable kart split is empirically confirmed (B Dasher +
Standard MR default, Shooting Star unlockable) - the other 11 characters' splits are
web-sourced names only, not verified which 2 of their 3 are the real starting pair.
`locations.py`/`items.py` now build their full location/item tables from this real data
instead of `Track N (TODO real name)` placeholders.

**MAJOR VALIDATION (2026-08-04): a real test generation succeeded.** Added a proper
`test/__init__.py` (`WorldTestBase`, per docs/world api.md's testing guidance) and ran it
via `py -m unittest worlds.mkds.test -v` against the reference AP checkout. All 6 tests
passed, including `test_fill` ("Generates a multiworld and validates placements with the
defined options") and both reachability tests. This means create_items(), set_rules(),
the region graph, and the fill/placement algorithm all work together correctly end to
end for the cup-goal case with default options - not just "imports without crashing," an
actual complete, logically-solvable multiworld got built. The working test file is saved
at `worlds/mkds/test/__init__.py` as part of the real source now, not just the throwaway
reference copy.

**Honest gaps still open in the code** (all marked with TODO comments in the files
themselves, not hidden): `create_items()` is an empty stub (no pool-construction logic
yet). `set_rules()`'s access rules are always-true placeholders (no real Progressive Cup
gating logic yet) and there's no `completion_condition` wired up yet, so a real generation
attempt would fail - haven't tried one yet, deliberately, since it wouldn't reveal much
beyond what's already known to be missing. `regions.py` wires every location
unconditionally rather than only the goal-required subset. `client.py`'s `game_watcher` is
entirely unimplemented pending task 5 (live game-state addresses - race results, mission
clears, TT ghost beats - none of which have been searched for yet).

---

## Task 5 investigation started (live game-state addresses), 2026-08-04 later session

Confirmed pure D-pad+A navigation works for the whole menu chain (title screen is the
only touch-driven screen; A alone selects "Single Player" since it's default-highlighted
- no need for the earlier touch-coordinate guessing at all). Full working chain: title
(A) -> Grand Prix or Time Trials (Down+A picks Time Trials) -> character (A) -> kart (A)
-> cup (A) -> track (A) -> confirm OK (A) -> race loads. Successfully got into an actual
live Time Trial race (Figure-8 Circuit) with a running lap/timer HUD.

Extended probe.lua with SCANSTART/SCANDIFF macro commands: SCANSTART stores a memory
region in a Lua-side table (not a file), SCANDIFF compares two stored scans and writes
ONLY the changed byte offsets - much more useful than raw hex dumps for finding live
state. Tested on the full heap region (0x021DA340, ~2MB) across a 3-second window while
sitting at the race start (kart not actually moving/being driven).

Result: 4139 changed bytes. The bulk of them (roughly the first ~1300 bytes worth,
0x021DA420 onward) form a dense, continuously-churning contiguous block - almost
certainly an audio buffer (engine idle sound), not game state, based on the pattern
(every byte changing, no structure, matches what an audio waveform looks like as raw
bytes). Not useful for finding race-state addresses - would need to specifically exclude
or route around this range in future scans.

**Promising unconfirmed lead**: further into the diff, a sparser cluster of single-byte
changes at addresses spaced EXACTLY 0x160 (352) bytes apart: 0x0235C0B4, 0x0235C214,
0x0235C374, 0x0235C4D4, 0x0235C634, 0x0235C794, 0x0235C8F4, 0x0235CA54, 0x0235CBB4,
0x0235CD14, 0x0235CE74 (11 addresses seen changing in this one window - there may be more
that didn't happen to change in this particular 3-second sample). Regular spacing like
this strongly suggests an array of per-entity structs (e.g. one per racer/kart) where the
same field within each struct is changing - worth investigating first, since if it's a
per-racer array, adjacent fields in the same struct could include position/placement,
which is exactly what's needed for race-finish detection.

**Not done yet**: identifying what that 0x160-object-array actually represents, isolating
an actual timer address (the diff didn't cleanly reveal one - values were either buried
in the audio-buffer noise or the timer may use a different encoding than expected),
mission-mode state, TT staff-ghost-beaten detection, or actually finishing a race/lap to
see completion-triggered changes (only sat at the starting line this session, didn't
drive). This whole area needs meaningfully more work - realistically it would go faster
with the user directly using BizHawk's own RAM Search tool interactively (built for
exactly this kind of hunt) rather than continued blind SCANSTART/SCANDIFF sampling.

Emulator left in a clean rebooted state at the end of this session.

### Follow-up: bit 16 isolated alone (2026-08-04, later)
Also confirmed: pure D-pad+A navigation works for the ENTIRE menu chain, including the
title screen ("Single Player" is default-highlighted, so a bare A works - no touch
needed anywhere except as a fallback). One recurring quirk: the very first button press
right after reaching a freshly-settled screen sometimes doesn't register, but a retry of
the exact same input works - seen a few times now, not fully understood, just routing
around it by retrying once.

Wrote bit 16 alone (`0x00010000`) and navigated to Select Class: **Mirror Mode appeared**
(the screen switches from a 3-option list to a 2x2 grid with Mirror as the 4th option).
This means bit 16 ALONE is sufficient for Mirror Mode - the earlier "bits 15+16 together"
finding was likely misleading; bit 15 was probably just incidental in that combined test,
not actually required. Revised `rom_addresses.py` to `UNLOCK_BIT_MIRROR_MODE = 0x00010000`
(bit 16 only) pending a one-more-check of bit 15 alone with this cleaner methodology, but
confidence is high given how directly this isolated result lines up.

### Bits 21-23 individually isolated (2026-08-04, same session)
Turns out the whole Daisy/Waluigi/R.O.B. group fits in just bits 21-23 (confirmed: 21-23
together still shows all 3, same as the wider 21-26 test did) - bits 24-26 are NOT part of
this group after all, still unaccounted for (unused/reserved, or something not yet found).
Individually:
- Bit 21 (`0x00200000`) = **Daisy**
- Bit 22 (`0x00400000`) = **Waluigi**
- Bit 23 (`0x00800000`) = **R.O.B.**

All three single-bit writes produced clean 9-character results (8 starters + exactly one
named bonus character), no corruption, even without a full reboot between tests -
suggests small, single-bit changes from an already-clean state don't trigger the
cache-desync issue seen earlier with extreme swings (all-zero <-> all-set). Updated
`rom_addresses.py` with these as individual constants.

**Character bit map is now fully resolved**: Dry Bones = bits 17-20 (exact bit within
that 4-bit range still not individually isolated, but only one candidate range now, worth
a final split if it matters later), Daisy = bit 21, Waluigi = bit 22, R.O.B. = bit 23.

### Item 4 attempt: kart-selection address search
Tried the same SCANSTART/SCANDIFF approach at the Kart Select screen, diffing memory
before/after pressing Right to cycle from "B Dasher" (kart 1/2) to "Standard MR" (kart
2/2). Result: 16030 changed bytes, same problem as the earlier race-timer hunt - looks
like the same kind of continuous animation/audio noise, no clean isolated byte flip
found. Not pursuing further via blind diffing - same recommendation as before, this would
go much faster with the user driving BizHawk's RAM Search tool directly (can filter by
"changed since last search" interactively across multiple cycles, which blind
SCANSTART/SCANDIFF sampling can't replicate well against this much background noise).

### Automation upgrade: NARROWSTART/NARROWTOGGLE/NARROWDUMP (2026-08-04)
Built proper iterative narrowing directly into probe.lua, replicating what a human does
with BizHawk's RAM Search tool by hand (repeated "changed value" filtering) but fully
scriptable: NARROWSTART takes an initial scan as "state A" and starts with every offset
as a candidate; NARROWTOGGLE narrows the candidate set each round to only offsets whose
value still matches the remembered reference for whichever state (A or B) the game was
just switched to - much stronger than a single before/after diff, since it requires
consistently flipping between exactly two values across many rounds, not just changing
once. This makes the whole class of "find the address for X" tasks self-serve - no more
depending on the user to drive RAM Search by hand.

**First real use, kart-selection index**: ran a fully automated reboot -> navigate to
Kart Select -> toggle Left/Right many times (varied wait durations between toggles, to
break any accidental sync with looping background music) -> dump. Went
2,120,896 -> 28,735 -> 1,380 -> ... -> 922 candidates, where it plateaued even with
timing variation (strongly suggests these are genuinely tied to kart selection, not
periodic noise - switching karts changes a lot: stats, 3D model, etc., not just one
index value, hence 922 rather than 1). Filtered the 922 down to 7 by looking for small
integer-looking values (0-3) rather than complex data. Best candidate:
**`0x02345DC8`** (value 0 for kart 1, 1 for kart 2 - a clean 0-indexed selection value).
Secondary candidates worth checking if the first doesn't pan out during client
implementation: `0x02345DCA` (inverted: 1->0, right next to the first, may be a related
field), `0x023745B8` (same 0->1 pattern, different region).

**Re-ran the same automated search at Character Select** (Mario <-> Luigi toggle,
varied timing again): converged even faster, 2.1M -> 25015 -> 164 -> 49 -> 43 -> 42
candidates. Notable: the surviving 42 heavily OVERLAP with the kart-index candidates -
`0x02345DC8`, `0x02345DCA`, `0x02348167`, `0x02358127` all showed up in both hunts.
This is a more valuable finding than either result alone: it strongly suggests these
aren't dedicated per-screen "kart index" / "character index" variables, but a shared,
generic menu-cursor/grid-position structure the game reuses across similar selection
screens. Relabeled in `rom_addresses.py` as `MENU_CURSOR_INDEX_CANDIDATE` accordingly.
Good news for automation going forward: whatever client code ends up reading "which
grid item is selected" can likely reuse the same address across cup/character/kart
select rather than needing three separate ones.

## BREAKTHROUGH: github.com/XorTroll/mkds-re (2026-08-04, user-provided link)

The user found a reverse-engineered decompile of MKDS's EU build (same author as the
xor.dev memory-cheat writeup that first gave us the unlock-flags address). This
completely changed the pace of task 5. Cloned to `reference/mkds-re/`.

**What's in it**: `re-export/include/mkds-eu-types.h` (~14800 lines of struct
definitions with exact field offsets) and `re-export/mkds-eu-symbols.x` (global variable
addresses for the EU build). Struct LAYOUTS are almost certainly region-independent
(same compiled logic); absolute global ADDRESSES are not directly reusable for our USA
ROM and need individual verification (see below - not a uniform offset).

### RaceStatus / DriverStatus - the big one
`g_GlobalMV` is a static global pointer that always points to the current `RaceStatus`
while a race is active (heap-allocated target, so always dereference fresh). EU symbol
address was `0x0217561C` - didn't work directly. Found the real USA address by scanning
a window around the EU address for heap-pointer-shaped values, then verified each
candidate by dereferencing and checking the RaceStatus-shaped fields (finished driver
count, place_driver_ids as a clean 0-7 permutation, a driver's cur_lap reading a sane
value). **Confirmed: `g_GlobalMV` (USA) = `0x021755FC`** (EU address minus 0x20).

`RaceStatus` (0x524 bytes) has exactly what task 5 needed: `finished_driver_count`,
`drivers[8]` (array of `DriverStatus`, 0x8C bytes each), `place_driver_ids[8]` (which
driver ID is in 1st/2nd/.../8th - directly gives race position), `race_ended`,
`mission_result`, `mission_win_delay_counter`, `mission_lose_delay_counter`.
`DriverStatus` has `cur_lap`, `race_finish_status`, `total_time`/`total_time_ms`,
`lap_times[6]`, `highest_reached_lap`, `race_progress`/`lap_progress` (fixed-point).
Full offsets now in `rom_addresses.py`.

**Verification method** (all live, against this exact USA ROM, during an actual race):
wrote `place_driver_ids` back as `04 03 05 02 01 07 06 00` - a perfect permutation of
0-7, essentially impossible by chance. `finished_driver_count` read as 7, which matched
reality (I'd left the kart idle for several minutes while investigating the repo, so all
7 CPU racers had almost certainly finished while the player hadn't). `time_running=1`
and a plausible large `time_frame_counter` both checked out too. This is about as solid
a confirmation as empirical testing can give without decompiling the USA binary directly.

**Not yet confirmed**: which index in `drivers[8]`/`place_driver_ids` corresponds to the
human player (guessed index 0, plausible but not independently proven). Time Trial mode
almost certainly reuses the same RaceStatus/DriverStatus structures - worth checking
there directly rather than treating it as a separate hunt.

### Kart-unlock mystery resolved
`enum ExtraKartUnlockState` (Invalid/NothingUnlocked/BasicUnlock/MediumUnlock/
TotalUnlock) and `enum CharacterKartUnlockFlags` confirm definitively: kart availability
is governed by a coarse 4-tier progress state, NOT a per-kart flag. This is authoritative
confirmation of what empirical testing already suggested (unlocking characters cascaded
to "all karts unlocked"). Strengthens the existing plan: implement kart randomization by
patching each character's *starting kart assignment* directly, since no native per-kart
flag exists to hook into at all.

### Mission Mode structure confirmed
`SaveDataSection_MissionRun`: 7 levels, each with 9 mission "stage entries" = 63 total
slots (not the 4-per-level placeholder guessed earlier - `locations.py` updated). Each
mission's runtime state (`StructMissionLevelStageInfo`) has separate one-byte `beaten`
and `rank` fields - a direct, authoritative match for Instructions.txt's "one check for
clearing, another for getting 3 stars" design. The compact save-file bit-packed version
exists too but isn't decoded - probably unnecessary since the runtime struct alone likely
suffices for live detection.

### Unlock-flags cross-check (no contradiction, just a different layer)
`mkds-eu-types.h` documents a `SecretFlags` enum with bit0=Star Cup, bit1=Special,
bit2=Leaf, bit3=Lightning, bit4=Mirror, bit5=Dry Bones, bit6=Daisy, bit7=Waluigi,
bit8=R.O.B. - a much MORE tightly packed layout than what we empirically verified at
`0x023CE2E0`. Traced this to `StructM.unlocked_secret_flags`, computed on-demand by
`GetCurrentUnlockedSecretFlags()` to drive the "you unlocked something!" popup - a
transient, derived value, not the persistent save representation. Doesn't invalidate our
empirical `UNLOCK_FLAGS_ADDRESS` findings (directly write-tested and confirmed working
multiple times over) - just a second, different-shaped view of similar information.
`g_SaveDataHolder` (EU: `0x0217AA08`) likely points to the actual canonical save struct
and could resolve the remaining individual-bit gaps (exact Special Cup bit, exact Dry
Bones bit) if it's ever worth chasing - not blocking anything right now since the
group-level masks already work for the goal-scoped design.

### RaceConfig / internal_course_id hunt - inconclusive, retry later
Found `RaceConfig` (has `internal_course_id`, `cup_idx`, and full mission fields
`mission_id`/`mission_task`/`mission_course`/`mission_character_id`/`mission_kart_id` -
exactly what's needed to know "which track/cup/mission is currently active") embedded
directly inside `RaceConfigManager.cur_race` at offset 0. EU symbol
`g_RaceConfigManager = 0x021759C0`. The same -0x20 offset that worked for g_GlobalMV did
NOT produce sane values here, and a NARROWSTART/TOGGLE search (toggling cup selection
with Left/Right on the cup-select screen) found zero changing candidates in a 4KB window
around the expected area.

**User clarified after the fact**: the game may have drifted into the attract-mode demo
video during that test (same idle-timeout issue documented earlier), meaning the
Left/Right presses might never have reached the actual cup-select screen at all - the
null result doesn't necessarily mean the address guess or region was wrong, just that the
test may have been invalid from the start. Worth retrying with explicit on-screen
verification (screenshot) before and after each toggle, not just trusting the input
landed. Deferred in favor of finishing client.py with what's already confirmed - the
"which track" piece is needed for full check-sending but isn't blocking everything else.

**Retried properly (2026-08-04) - still inconclusive, now with real confidence it's the
region that's wrong, not the test methodology.** Chained everything into one macro to
rule out attract-mode interference, and verified every step with screenshots this time
(catching and correcting an off-by-one navigation error along the way - the first
"confirm" was actually still the kart->cup transition, not a track confirmation).
Properly re-based at the real cup-select screen, tried: cursor movement between tracks,
confirming a specific track (reaching the OK/BACK screen), and finally actually pressing
OK to start the race - all compared against a fresh baseline via NARROWSTART/TOGGLE
across an 8KB window (`0x02175000`-`0x02177000`). Zero candidates changed at every single
stage, including after actually starting the race. This is a strong signal the region
itself is wrong (g_RaceConfigManager's USA address doesn't follow the same -0x20 offset
that worked for g_GlobalMV), not that the test methodology was flawed. Concluding this
specific hunt here rather than continuing to guess regions - would need either a wider
static-region scan (RaceConfigManager's pointer itself is a static global like
g_GlobalMV, but its heap-allocated target could be far from where we've looked) or a
fresh NARROWSTART approach scanning a much larger static window. Left for a future
session; not blocking other work.

### client.py implemented (2026-08-04)
Real logic now, not stubs. `_apply_received_items`: ORs together unlock bits for every
Character/Progressive-Cup item currently received (Progressive Cup order comes from new
slot_data - `fill_slot_data()` added to `__init__.py` sending `required_cups_in_order`)
and guarded-writes the result to `UNLOCK_FLAGS_ADDRESS`. `_check_race_result`:
dereferences `GLOBAL_MV_POINTER_ADDRESS` each tick, validates it's heap-range (no race =
skip), tracks the pointer value itself to detect a new race instance (resets per-race
dedup), and checks `race_ended` + `place_driver_ids[0] == PLAYER_DRIVER_ID` for a
confirmed win. Re-ran the full test suite after wiring this in - still passes clean
(confirms `worlds._bizhawk` imports fine in this environment too, not just our own code).

Two honest gaps left in the code itself (marked with TODOs, not hidden): can't yet send
the actual LocationChecks message for a detected win (no "which track" address - see
above), and Leaf/Lightning Cup can't be unlocked independently (shared bit group).
Karts and Time Trial items are received but not yet applied (karts need the
starting-kart-patch mechanism; Time Trial has no goal/location design yet).

### Leaf Cup / Lightning Cup individually isolated (2026-08-04)
Used the same proven bisection technique as the character bits. Bits 7-9 (`0x380`)
unlocked Leaf Cup only; narrowed further - bit 7 alone: nothing, bit 8 alone
(`0x100`): **Leaf Cup**. Bits 10-13 similarly narrowed - bits 10 and 11 alone: nothing,
bit 12 alone (`0x1000`): **Lightning Cup**. Bits 7, 9, 10, 11, 13 appear unused/reserved
(the ones tested individually were confirmed inert; 9 and 13 weren't tested alone but
aren't needed now that both real bits are found). `rom_addresses.py`'s
`CUP_UNLOCK_MASKS` updated to use the individual bits - the "unlocks both at once" gap
from earlier is fully resolved. All 8 cup-gated unlocks (Star, Special, Leaf, Lightning,
Mirror, plus the 3 individually-isolated characters) now have clean single-bit or
verified-group addresses; only Dry Bones still uses an unverified 4-bit group as a
pragmatic stand-in (see the CHARACTER_UNLOCK_BITS comment).

The underlying design conclusion from earlier still stands regardless: kart availability
doesn't look independently flag-gated in vanilla MKDS (unlocking characters cascaded to
"all karts unlocked" rather than gating specific karts), so the plan remains to implement
kart randomization via patching each character's starting-kart assignment directly once
that address is found - not blocked on anything new, just still an open address hunt.

---

## FINAL STATUS SUMMARY, end of session 2026-08-04 ~04:00

**Full bit map of `0x023CE2E0` as currently understood** (all offsets within the 32-bit
word at that address, "ARM9 System Bus" domain):

| Bits | Effect | Confidence |
|---|---|---|
| 0-3 | Star Cup | High (isolated down to a 4-bit group) |
| 4-6 | Special Cup | High by elimination, exact bit(s) untested |
| 7-13 | Leaf Cup + Lightning Cup together | High for the group; which sub-bits map to which cup untested |
| 14 | No effect alone | High |
| 15-16 together | Mirror Mode | High; bit 15 alone confirmed inert, bit 16 alone untested |
| 14+16 together | ALSO unlocks Lightning Cup (in addition to the 7-13 path) | Confirmed but unexplained overlap |
| 17-20 | Dry Bones (+ correlated "all karts unlocked" side effect, cause not isolated) | High for Dry Bones; kart cascade cause unconfirmed |
| 21-26 | Daisy + Waluigi + R.O.B. together | High for the group; individual bits untested |

Baseline (fresh save, all zero): 8 starter characters, Mushroom/Flower/Shell/Banana cups,
no Mirror. `0x07FFFFFF` (bits 0-26) = everything unlocked, matches the known community
"unlock everything" cheat code.

**Old summary below is superseded by this table where they conflict - kept for narrative
detail on how each finding was reached.**

## STATUS SUMMARY as of end of autonomous session, 2026-08-04 ~03:30

**Where task 4 (unlock-flags bitfield) actually stands:**

Confirmed with reasonable confidence:
| Bit range | Effect |
|---|---|
| 0-6 | No character effect (checked). Cup/kart effect unknown - cup screen unreachable this session (see below). |
| 7-13 | Untested this session. Prime suspect for Star Cup, Special Cup, Leaf Cup bits. |
| 14 | No effect alone. |
| 15+16 together | Mirror Mode. Neither alone (at least bit 15 alone confirmed inert; bit 16 alone untested). |
| 14+16 (as part of 14-16 combined) | Lightning Cup - needs bit 14 AND 16 together, not independent bits. Not a clean bitfield in this sub-range - treat with caution. |
| 17-20 | Dry Bones. Also correlated with an "all karts unlocked" side effect (cause not confirmed - could be Dry Bones' bit specifically, or something else in this range). |
| 21-26 | Daisy, Waluigi, R.O.B. together (which of the 6 bits map to which character not yet individually isolated). No kart cascade from this range. |

**UPDATE 2026-08-04 ~03:45**: Bits 7-13 (0x3F80) tested with full navigation now working
- unlocked **both Leaf Cup AND Lightning Cup** (Star/Special still locked), no character
effect. So Lightning appears reachable two different ways (bits 7-13, and separately the
14+16 combination found earlier) - not fully understood why, not chasing that mystery
right now. Star and Special cups still unaccounted for - now checking bits 0-6 for cups
specifically (only characters were checked for that range before).

**UPDATE 2026-08-04 ~03:50**: Bits 0-6 (0x7F) unlock **Star Cup and Special Cup** (no
character effect, confirmed earlier). This completes cup-group mapping - all 8 cups now
accounted for: Mushroom/Flower/Shell/Banana unlocked by default; Star+Special in bits 0-6;
Leaf+Lightning in bits 7-13 (Lightning also separately reachable via bits 14+16 combined -
unexplained overlap, not chasing it further). Now narrowing 0-6 to separate Star from
Special individually.

**UPDATE 2026-08-04 ~03:55**: bits 0-3 unlock Star Cup specifically (Special still locked)
- so Special Cup's bit is in 4-6, unconfirmed which exact one, not tested directly (high
confidence by elimination given 0-6 together gives both and 0-3 alone gives only Star).

**Stopping the granular bit-hunt here for tonight.** All 8 cups and all 4 bonus characters
are now mapped at the group/range level (table below), which is enough to design against.
Precise single-bit isolation for cup members and the 21-26 character group can happen
during actual client implementation (task 6) rather than continuing to burn this session
on ever-finer manual bisection - diminishing returns, and a couple of genuine oddities
(Lightning's dual path, the 14-16 AND-logic) are worth the user's eyes rather than more
solo guessing.

**Not yet found / still open**: individual bit isolation within 21-26 (know the group
unlocks Daisy+Waluigi+R.O.B. together, not which bit is which character) and within 4-6
for Special Cup specifically. Bit 16 in isolation (untested). Whether 14-16's apparent
AND-logic generalizes elsewhere or is a one-off - Lightning Cup being reachable two
different ways (7-13 AND the 14+16 combo) is genuinely unexplained. Full kart-unlock
mechanism (increasingly looks like it may not be independently flagged at all in vanilla
MKDS - see the design decision note above about randomizing starting-kart assignment
instead).

**Tooling status**: `reference/ram_probe/probe.lua` supports read snapshots, memory
writes, `client.reboot_core()`, scripted button presses (`PRESS`), touch taps (`TOUCH`),
waits, and screenshots I can read myself - all confirmed working. One real bug already
found and fixed (a runaway loop counter that hung the whole script - if the script ever
seems stuck/unresponsive again, that class of bug is the first thing to suspect).

**RESOLVED (user correction, 2026-08-04 ~03:40)**: Kart Select's confirm is the **A
button, not a touch tap** - I'd been assuming it was touch-only like the title screen,
which was wrong and cost a lot of wasted attempts. Full reliable navigation chain,
confirmed working end to end from a fresh reboot:
```
REBOOT
WAIT 450                    (must wait ~7-8s for the title menu to become interactive)
TOUCH 128 20 8 40            (taps "Single Player" - title menu IS touch-driven)
WAIT 40
PRESS A 5 60                 (confirms "Grand Prix" on the mode-select cursor menu)
PRESS Down 5 20               (cursor: 50cc -> 100cc)
PRESS Down 5 20               (cursor: 100cc -> 150cc)
PRESS A 5 90                 (confirms 150cc, lands on Character Select)
PRESS A 5 90                 (confirms default character, lands on Kart Select)
PRESS A 5 90                 (confirms default kart, lands on Cup Select)
```
Chaining the whole thing into one macro call (no round-trip gaps for me to think between
steps) was also important - splitting it into separate calls kept losing the race against
the ~7-8s attract-video idle timer. B reliably backs up one screen at a time through this
whole chain for re-checking earlier screens without a full reboot.

**What I did instead while waiting**: updated `locations.py` with the 4 confirmed real
Mushroom Cup track names (previously placeholders). Left the emulator in a clean
rebooted state. Did not touch Instructions.txt, items.py structure, or options.py this
session - those are unaffected by tonight's findings so far.

**Next steps when resumed**: (1) finish isolating bits 0-13 for cups (needs cup-screen
access), (2) isolate bit 16 alone and confirm/refute the AND-logic theory for
Mirror/Lightning, (3) isolate individual bits within 21-26 for Daisy/Waluigi/R.O.B.
specifically, (4) once character/cup bits are fully mapped, revisit the kart-unlock
mechanism question before starting the client/rules implementation (tasks 6-7), since
that may need a different technical approach (starting-kart randomization patch) rather
than a native flag to hook into.

### Bits 14-16 (0x0001C000) isolated further
Result: Mirror Mode + Lightning Cup, but NOT Dry Bones this time - and notably, no kart
cascade either. Supports the theory that the "all karts unlocked" side effect is
specifically triggered by a *character* becoming newly unlocked, not by cups/Mirror. So:
- Dry Bones' bit -> somewhere in bits 17-20 (the rest of the earlier 14-20 range).
- Mirror + Lightning -> both within bits 14-16.
Next: split 14-16 further (bit 14 alone) to separate Mirror from Lightning.

### Bit 14 alone, then bits 15-16 alone
- Bit 14 alone: nothing unlocked. Likely unused/reserved, or only meaningful combined
  with other bits.
- Bits 15+16 together: Mirror Mode only (no Lightning this time).
- Recall bits 14+15+16 together: Mirror + Lightning.

This does NOT fit a simple "each bit is an independent flag" model - bit 14 alone does
nothing, but adding it on top of 15+16 (which already gives Mirror) additionally unlocks
Lightning. That looks more like Lightning requires bit 14 AND bit 16 (or some specific
multi-bit combination) rather than being its own independent single bit. Possible this
whole word isn't a clean per-item bitfield at all, and some sub-ranges encode small
combined/threshold values instead of independent booleans. Testing bit 15 alone next to
find out whether Mirror is purely bit 15, or also needs help from bit 16.

---

## Session 2026-08-04 (later): mission flags resolved, RaceConfig struct fully mapped (address still open), kart design fork identified

Picked up "tackle all three" (RaceConfig address, kart-assignment mechanism, mission
win/lose semantics) plus general research-before-emulator-time, per user instruction.
Researched `mkds-re` deeply before touching the emulator, then did one round of live
verification. Net result: one item fully resolved, one substantially de-risked (full
struct layout known, live address still open), one turned out to be a real design fork
rather than a pure address hunt.

### Mission win/lose flags - RESOLVED (research only, no emulator needed)
`enum DriverStatus_Flags` (mkds-re): `IsPlayer=1`, `Unk1=2`, `WrongDirection=4`, `Unk3=8`,
**`MissionRunWinDelay=16`**, **`MissionRunLoseDelay=32`**, `PerformFinish=64` - bits within
`DriverStatus.flags_and_respawn_id` (offset 0x30, already-verified struct). Added as
`DRIVERSTATUS_FLAG_MISSION_WIN_DELAY`/`_LOSE_DELAY` to `rom_addresses.py`, and wired into
a new `client.py._check_mission_result()` that reads the player's own `DriverStatus` entry
via the SAME already-verified `GLOBAL_MV_POINTER_ADDRESS` pointer chain `_check_race_result`
uses - no new address needed for detection itself. Not live-tested against a real mission
attempt yet (research-confirmed, not emulator-confirmed), and still can't send the actual
LocationChecks message - same "which mission is this" gap as race results (needs
RaceConfig, see below). Full test suite still passes after wiring this in.

### RaceConfig - full struct layout now known, live USA address still unresolved (3rd hunt)
Reading `mkds-eu-types.h` directly (not just grepping for names) paid off enormously.
`struct RaceConfig` (0x1E8 bytes) fields, in addition to the already-known
`internal_course_id`/`cup_idx`:
- `cc_type` (0x10), `cur_mission_level` (0x54), `cur_mission_stage` (0x55),
  `mission_id`/`mission_character_id`/`mission_kart_id` (0x2E/0x32/0x33) - everything
  needed to know exactly which of the 63 mission slots or which track/cup is active.
- **`player_driver_id`** (0x62, u8) - a DIRECT, authoritative answer to "which drivers[]
  index is the player", superseding the old `PLAYER_DRIVER_ID=0` guess-and-infer approach.
- `racer_entries` (0x68, `DriverConfig[8]`, 0x30 bytes each) - each entry has
  `character_id` (0x0) and `kart_id` (0x4): the actual per-driver race-setup assignment.
  This is the write target for kart-item enforcement, if/when that gets built.

Also found `CharacterKartContext` (0xB4 bytes, live UI/render state, NOT the same as
`RaceConfig.racer_entries` - this is the on-screen preview state as you browse
character/kart select, one per racer via `GetCharacterKart(driver_id)`). Has `char_idx`
(0x0) and `kart_idx` (0x4) as **independent** fields (kart_idx not derived from char_idx) -
confirms the engine has no hard-coded restriction tying a kart to one character, matching
Instructions.txt's "no engine-level restriction" claim. Also has `kart_idx_mod_3` (0x68,
u16) suggesting global kart ids are laid out as `character_slot*3 + (0/1/2)`.

Also found `StructB488` (`g_GlobalB488`, EU 0x0217B488) - a WFC-ranking-flavored session
record (`player_global_rank`, `player_total_rankpoints` nearby) that ALSO happens to cache
`racer_character_ids[8]`/`racer_kart_ids[8]`/`player_character_id`/`player_kart_id`. Useful
as a secondary cross-check but not the primary target - it's a derived record, not the
race-setup input.

**Live verification (3rd attempt at the address, with much better target knowledge this
time):** Found `raceconfig_hyp.txt` etc. from an earlier attempt today - a dump at
`0x021759A0` (EU `g_RaceConfigManager` minus the same -0x20 that worked for `g_GlobalMV`)
showing 6 heap-pointer-shaped candidate values, individually dereferenced
(`cand2.txt`-`cand6.txt`, `candidate1_header.txt`). None was a clean match by inspection
alone. Root-caused WHY the original NARROWSTART/TOGGLE attempts on this hunt all came back
with 0 candidates (`raceconfig_result.txt`/`rc2_result.txt`/`rc3_final.txt`): those scans
targeted the STATIC region containing the pointer itself, but a stable singleton pointer's
VALUE doesn't change once allocated - only fields INSIDE the heap struct it points to do.
That's a real methodology fix worth remembering for future pointer hunts.

Picked the closest-looking candidate (candidate 4: static slot `0x02175604` -> heap addr
`0x023D6298`) and live-tested it properly:
- At rest (main menu), offset+0x4 read `2` (plausible `cup_idx`).
- Navigated fresh through Single Player -> Grand Prix -> 150cc -> Cup Select -> Character
  Select (confirmed via screenshot - landed one screen further than intended, the
  recurring off-by-one nav quirk, but usable). offset+0x4 had changed to `0` while every
  other byte in the 0x20-byte window stayed frozen - a real, semantically-meaningful
  change, not noise.
- Backed out with B, intending a controlled cup-cursor toggle test - instead unexpectedly
  ended up mid-race as Bowser (the B-press/timing chain didn't land where planned; not
  fully understood, possibly B behaves differently than "back" at that exact screen, or a
  buffered input carried through a cutscene-skip). Silver lining: an unplanned but very
  clean cross-check opportunity, since I now knew ground truth (racing as Bowser,
  `CharacterId_Bowser=3`).
- **Result: candidate 4's `racer_entries` region (offset 0x68+) read all zeros throughout
  the entire race** (steering inputs don't touch it, as expected for a setup struct - but
  it should have shown `character_id=3` SOMEWHERE if this were the live `cur_race`). This
  rules out candidate 4 as the actively-used struct. Hypothesis: it's `RaceConfigManager.
  next_race` (offset +0x1E8 from `cur_race`) rather than `cur_race` itself - which would
  explain both the real cup_idx-shaped change (next_race IS what's being staged as you
  navigate menus) and the frozen/empty racer_entries during an active race (next_race
  isn't used until the FOLLOWING race). Tested the obvious follow-up (`cur_race` = candidate
  4's address minus 0x1E8 = `0x023D60B0`) - came back **entirely zero**, disproving that
  specific shift. So candidate 4 is *something* real and menu-selection-reactive, but not
  proven to be RaceConfigManager's cur_race, and the -0x1E8 shift guess was wrong.

Added a new `FINDBYTES <addr> <len> <hex_pattern> <label>` command to `probe.lua` (raw
byte-pattern search across a region, writing every matching address to a file) - a
reusable capability for hunting a struct by an expected field VALUE rather than by
watching it change. **Not usable yet - needs a script reload in BizHawk's Lua Console
before this command will be recognized** (the running instance still has the old code).

**Recommended next step** (either path avoids more static-analysis guessing):
1. After a reload, `FINDBYTES` for `03000000` (Bowser's `character_id`) across
   `HEAP_RANGE` while actually racing as a known character - any hit followed by a
   plausible small `kart_id` 4 bytes later is a strong candidate for `racer_entries[N]`,
   which pins the whole `RaceConfig` by working backwards `0x68 + N*0x30` bytes.
2. Or, without needing a reload: a full NARROWSTART/TOGGLE across the whole heap comparing
   two COMPLETE race setups with different characters (not just menu-cursor toggling like
   the earlier `char_idx`/`kart_idx` attempts) - more expensive (needs full menu
   navigation twice) but uses only already-loaded, already-proven commands.

Stopping here for this session rather than continuing to burn turns on live guessing -
this is the 3rd distinct hunt for this one address, each with progressively better target
knowledge but no confirmed result yet. The struct-layout knowledge gained is real,
substantial, and immediately useful regardless (see `rom_addresses.py`).

### Kart-item enforcement - identified as a design fork, not just an address gap
Vanilla's kart-select UI only ever shows the CURRENT character's own 3 karts (tier-gated
via the existing `ExtraKartUnlockState` system - see earlier notes), never a path to use a
different character's kart. `CharacterKartContext` proves the ENGINE has no hard-coded
restriction (kart_idx and char_idx are independent fields) - but the UI never exposes that
freedom to the player.

This means:
- **"Yes only each character's unique karts"** (Instructions.txt's simpler kart option) is
  fully achievable right now with zero further address hunting: force the existing global
  tier to `TotalUnlock` as Kart items are received, and vanilla's own per-character 3-slot
  picker does the rest correctly.
- **"Yes all"** (any character, any unlocked kart) has no vanilla UI path at all. Real
  options: (a) an ASM-level patch to the kart-select cursor/bounds-check logic (candidate
  function: `CheckExtraKartUnlockFlagsWith`, EU `0x02056DAC`, USA not found) to let the
  picker browse all ~36 karts regardless of current character, or (b) write the player's
  intended kart directly into `RaceConfig.racer_entries[player_driver_id].kart_id` right
  before the race starts - but this still needs some way for the player to EXPRESS which
  of their received karts they want, since vanilla's picker can't offer all 36. Neither
  option is implemented. Flagging this explicitly rather than silently picking one, since
  it changes shipped behavior for a mode Instructions.txt explicitly specifies - worth the
  user's input if/when this becomes the active blocker, rather than more solo guessing.

### Where things stand after this session
| Item | Status |
|---|---|
| Mission win/lose detection | Resolved (research) - wired into client.py, not live-tested |
| RaceConfig struct layout | Fully known (all relevant offsets) |
| RaceConfig live USA address | Still open - 3rd hunt, candidate 4 ruled out as `cur_race`, `FINDBYTES` tool ready for next attempt (needs script reload) |
| Kart starting-assignment address | Superseded by a bigger question - see design fork above. "Yes only own karts" needs no new address at all (tier system suffices). "Yes all" needs either an ASM patch or a UX design for free kart selection. |
| Mission-slot mapping (locations.py) | `MISSIONS_PER_LEVEL` correction (4->9) confirmed already applied |

---

## Session 2026-08-04 (later still): Time Trial + Mission goal legs implemented, two real bugs caught by new test coverage

With RaceConfig's live address stuck pending a script reload (see above), moved to a
concrete code task that didn't need the emulator at all: `rules.py` only handled the Cups
goal leg; Time Trial and Mission Mode were still `TODO`. `items.py` already had
`Progressive Time Trial` (count=32) sitting unused, and `options.py`/`locations.py` already
had everything else needed (full `Goal` enum + validation, real 32-track and 63-mission
location data) - this was genuinely just wiring, not new design, EXCEPT for one real
decision: missions have no `Progressive Mission` item and never will (Randomize Mission
Mode only shuffles WHICH mission occupies each slot - it doesn't gate access to Mission
Mode itself), so mission locations use an unconditional access rule regardless of
required-ness; only Cups and Time Trials are item-gated, via the same "Progressive X,
position N" pattern.

Added `choose_goal_required_time_trials`/`choose_goal_required_missions` (mirroring
`choose_goal_required_cups`), wired their output into `decide_goal_requirements`'s
`required_locations` union, added access rules and completion-condition legs for both in
`set_rules`, and added the missing `Progressive Time Trial` pool sizing to
`__init__.py`'s `create_items`.

**Wrote real test coverage for the first time** - `worlds/mkds/test/__init__.py` previously
had no options-driven test classes at all (just a bare `MKDSTestBase`), so every goal type
other than the untested default had literally never been generated. Added one test class
per goal type (`TestCupsAll`, `TestCupsCount`, `TestMissionModeComplete`,
`TestMissionsCount`, `TestTimeTrialsAll`, `TestTimeTrialsCount`, `TestCombination`) with
real `assertBeatable` progression checks, following the pattern in `worlds/kdl3/test/
test_goal.py`. This immediately paid off - it caught two genuine, previously-latent
structural bugs that the old vacuous default test (see below) never could have:

1. **`create_regions` created every location in `location_table` unconditionally**,
   regardless of whether it was actually goal-required for the seed - already flagged by
   its own TODO ("this is NOT the final behavior yet") and a matching TODO in
   `rules.py`, but never actually fixed. Since `create_items` only sizes the pool to
   `len(required_locations)`, any seed where required_locations was smaller than the full
   ~198-location table (i.e. almost every seed except `cups_all` with time trial/mission
   also maxed out) hit `FillError: Unable to fill all locations`. Fixed by making
   `create_regions` skip any location not in `world.required_locations` - matching
   Instructions.txt's actual design (non-required content isn't a real AP location at
   all, not just "doesn't need an item"). `rules.py`'s `set_rules` simplified to match -
   it now only iterates `required_locations` instead of the full table, since every
   instantiated location is required by construction.

2. **Off-by-one in the "Progressive X, position N" access rule**: `position =
   required_X_in_order.index(x) + 1`, i.e. the FIRST required cup/track needed 1 copy of
   Progressive Cup/Time Trial ALREADY HELD just to be reachable. With nowhere else in a
   self-contained single-player seed for that first copy to go (every location needs
   >=1 held, nothing is reachable with 0), `distribute_items_restrictive` reliably failed
   on the very last unplaced item with nowhere valid left to put it. Fixed by dropping the
   `+ 1` - position is now 0-indexed, so the first required entry needs 0 copies (it's the
   bootstrap into the chain, matching "you always have somewhere to start"), the second
   needs 1, etc. Also switched the completion-condition legs for Cups/Time Trials from
   `state.has(item, player, len(required))` to `all(state.can_reach_location(loc, player)
   for loc in required_locations)` - consistent with the Mission leg's condition, and more
   correct than the old flat item-count (which was stricter than necessary: reaching the
   LAST required location under the corrected 0-indexed rule only ever needs count-1
   copies, not count).

**Why the old tests never caught either bug**: `WorldTestBase.run_default_tests` is `self.
options or (setUp overridden) or (world_setup overridden)` - since the old `MKDSTestBase`
had no `options = {...}` (empty dict, falsy) and didn't override either method, its
inherited `test_fill`/`test_all_state_can_reach_everything`/`test_empty_state_can_reach_
something` all silently no-op'd (`if not (self.run_default_tests and self.constructed):
return`). The "6 tests, all passing" seen throughout this whole session was never actually
exercising real generation - worth remembering for any AP world: a `WorldTestBase`
subclass needs its own `options = {...}` (even `{}`-equivalent-but-non-empty won't help;
it needs to be truthy, or a custom `setUp`/`world_setup`) before its inherited tests do
anything at all.

All 34 tests pass now (`py -m unittest worlds.mkds.test -v` from `reference/Archipelago`
after re-syncing `worlds/mkds/`), covering real generation for every goal type.

---

## Session 2026-08-04 (still later): RaceConfig address BREAKTHROUGH - checks can now actually be sent

User fixed a BizHawk controller-conflict issue (their physical controller had been
interfering with scripted input, likely explaining earlier navigation oddities including
the "B press led into an active race" incident from the previous RaceConfig attempt).
Verified scripted PRESS still works correctly post-fix, then used the now-reliable input
to properly redo the cup-select toggle test that got derailed earlier today.

### The actual resolution
Full-heap NARROWSTART/TOGGLE on cup-cursor movement (same technique that found char_idx/
kart_idx earlier) converged to 2118 candidates - too noisy to read directly (cup-select
has far more visual/rendering state changing per cursor move than character-select did).
Locally filtered the NARROWDUMP output (address, value-at-A, value-at-B) for entries
differing by exactly 1 - collapsed to 6 candidates immediately. One
(`0x02374560`, in the same `0x0237xxxx` region as several `char_idx_result.txt` hits from
earlier - a shared "menu state" area) behaved exactly like a real cursor index: went 0->1
moving right onto Flower Cup, then correctly STAYED at 1 when tested against a locked,
unreachable Star Cup (cursor blocked from moving further, confirmed via screenshot) -
consistent, non-coincidental behavior for a real index.

This address turned out to be a TRANSIENT, cup-select-screen-local variable, though - its
value became garbage the moment the screen transitioroned to loading (heap block freed/
reused). Not directly useful, but confirmed the RIGHT general neighborhood and technique.

**The actual breakthrough came from a completely different angle**: with a race now
active (Flower Cup, Desert Hills, as Mario), dereferenced the already-proven
`GLOBAL_MV_POINTER_ADDRESS` to get RaceStatus's live heap address, then did a **local
Python search** (not more emulator round-trips) over a READAT dump of a 64KB static
region for the exact 4-byte pointer value - came up empty. Widened to 256KB - still
empty. g_RaceConfigManager's static pointer, wherever it is, does not sit anywhere near
its EU-derived region for the USA build (unlike g_GlobalMV's tiny -0x20 shift).

Pivoted to a fundamentally different strategy: instead of finding the STATIC pointer,
searched a wide HEAP window (READAT 64KB starting near RaceStatus's address, parsed
locally in Python) for the exact byte pattern of a plausible `RaceConfig` struct
(`internal_course_id` < 40, `cup_idx` == the actually-selected cup, `race_mode` == 0,
4-byte aligned). Found a cluster of matches with `course_id=5, cup_idx=1` at
`0x0237F19C` - exactly matching ground truth (Flower Cup, Desert Hills). Cross-checked
`player_driver_id` (read 0) and `racer_entries[0].character_id` (read 0 = Mario) - both
correct. **Computed the offset from RaceStatus's address to this candidate: exactly
`0x43F8`.**

Verified this offset is STABLE, not a one-off: rebooted, started an entirely different
race (Mushroom Cup, Figure-8 Circuit), computed `<fresh RaceStatus address> + 0x43F8`,
and it again read the exactly-correct `cup_idx=0, internal_course_id=1` - a second
independent exact match (cup_idx has 8 possible values; two-for-two is not a plausible
coincidence).

**Working mechanism**: `race_config_addr = <dereference GLOBAL_MV_POINTER_ADDRESS> +
0x43F8` (`RACECONFIG_OFFSET_FROM_RACESTATUS` in `rom_addresses.py`). This is a relative-
offset shortcut, not a real static-pointer chain - flagged with an explicit residual-risk
caveat in `rom_addresses.py` (untested across different unlock states / save files /
heap activity from received items). Good enough to ship on; revisit if it ever misbehaves.

Some fields further into the struct (e.g. what should be `display_mode` around offset
0xC) didn't match the expected small-int shape in the second test - and CPU driver slots
1-7 showed implausible/uninitialized-looking `character_id`/`kart_id` values in both
tests, while the player's own slot 0 was always clean and correct. Not fully explained -
possibly CPU assignment happens later/elsewhere, or the struct at this exact relative
offset isn't byte-for-byte `RaceConfig` beyond the first ~12 bytes. Doesn't block
anything: only `internal_course_id`/`cup_idx`/`cur_mission_level`/`cur_mission_stage`/
`player_driver_id` are needed for location-mapping, and all of those read correctly.

### What this unblocked
- **`client.py` now actually sends `LocationChecks`** for both race wins (`"{track} -
  1st Place"`, gated by `rom_addresses.CONFIRMED_COURSE_IDS` - only Figure-8 Circuit=1
  and Desert Hills=5 mapped so far, the other 30 need the same "start a race, read
  internal_course_id, note the track" data collection, no longer a technical blocker) and
  mission wins (`"{mission} - Clear"`, using `cur_mission_level`/`cur_mission_stage` to
  reconstruct the exact mission location name - not yet live-tested against a real
  mission attempt, only against the research-confirmed win-flag bits).
- Both paths cross-check against `ctx.slot_data`'s `required_race_tracks`/
  `required_missions` before sending - **catching a real bug found while wiring this up**:
  `rules.py`'s `decide_goal_requirements` never added individual `"{track} - 1st Place"`
  locations to `required_locations` at all, even though Instructions.txt explicitly lists
  races as their own check-granting category alongside cups ("finishing first in any
  race... each track can only give one check", counted separately from cups in the
  item-count formula). Fixed: every track within a required cup is now also a required
  race-win location (access-gated the same as its parent cup - you need the cup unlocked
  to attempt any of its tracks, but winning a specific one doesn't grant further
  progression on its own; completion still only cares about cup WINS, not every race).
  `world.required_race_tracks` is now sent via `fill_slot_data()` alongside the existing
  cup/time-trial/mission slot data, specifically so client.py can verify a resolved track
  is actually in-scope before sending - the FULL `location_table` always has all 198
  locations regardless of seed, so table membership alone doesn't confirm a location is
  real for THIS seed (the same class of bug existed in the mission-check path too,
  fixed the same way).
- Noted in passing: the new `required_race_tracks` computation uses the fixed vanilla
  `TRACKS_BY_CUP` regardless of the `Randomize Cups` option - correct for the default
  "unrandomized" mode, not yet extended for the other two (cup-track shuffling isn't
  implemented anywhere in the codebase yet, not a regression from today's work).

All 34 tests still pass after these changes. `client.py` compiles cleanly.

### What's left
- Fill in the remaining 30 `CONFIRMED_COURSE_IDS` entries (mechanical, not blocked -
  just needs 30 more "start a race, read the value" data points).
- Live-verify mission win detection and the `cur_mission_level`/`cur_mission_stage`
  reconstruction against an actual mission attempt (currently research + address-
  mechanism confirmed, but never triggered a real mission win in-game this session).
- Mission "3 Stars" checks still aren't sent - needs `StructMissionLevelStageInfo.rank`'s
  live address (not looked for yet).
- The CPU-driver-slots-look-wrong oddity in `RaceConfig.racer_entries` - not blocking,
  but worth understanding before ever trying to WRITE to that array (e.g. for kart-item
  enforcement, see the earlier kart design-fork notes).
- Real cup-track randomization (the `Randomize Cups` option) isn't implemented anywhere -
  pre-existing gap, newly relevant now that `required_race_tracks` needs a real mapping.

---

## Session 2026-08-04 (continued): BizHawk touch input regression, real generation testing finds and fixes an item-overflow bug

### BizHawk touch input stopped working
While trying to bulk-collect more `CONFIRMED_COURSE_IDS` entries via Time Trial mode (see
below - this worked well for two tracks), an attempted third sample derailed into a WFC
"choose a group" screen instead of the expected race. Recovered via reboot and re-tested
input from a verified-clean, screenshot-confirmed main menu: `PRESS A` did nothing (this
turned out to be expected - the main menu has always been touch-only, per much earlier
NOTES.md findings; my apparent earlier "confirmation" that `PRESS A` worked post-controller-
-fix was actually testing a different, already-in-game screen, not this one). More
concerning: `TOUCH 128 20` - the exact coordinate with a long, previously-reliable history
in this session's own logs - also did nothing, with no Lua-level error, across 5 attempts
(original coordinate at two hold durations, plus a different coordinate/duration). This
looks like a regression from the controller setting change the user made earlier today,
not a coordinate mistake - flagged to the user rather than continuing to guess blindly.
**Emulator is currently sitting idle at the real main menu** (confirmed via screenshot,
not attract mode) - safe, unharmed state, just can't proceed past it via scripted input
right now.

### Time Trial mode IS usable for course_id data collection (while it worked)
Confirmed Time Trial mode lets you pick an individual track directly (unlike Grand Prix,
which bundles all 4 of a cup's tracks into one sequential run) - `Select Mode -> Time
Trials -> Time Trials (submenu) -> character -> kart -> cup -> individual track list with
OK/BACK`. Got two clean samples before the input regression:
- **Yoshi Falls: internal_course_id = 18**
- The Time Trial offset from RaceStatus is **NOT** the same `0x43F8` found for Grand Prix -
  makes sense in hindsight (Time Trial has no CPU racers, so less gets allocated in
  between RaceStatus and RaceConfig). Found empirically the same way as before (local
  Python search over a wide READAT dump for a plausible `internal_course_id`/`cup_idx`
  pattern near the fresh RaceStatus address): **`0x0234E220`**, which is RaceStatus+`0xE0`
  for that specific race. Driver slots 1-7 read cleanly as all-zero this time (no CPUs
  exist in Time Trial, so zero is actually correct here, unlike Grand Prix's unexplained
  garbage in those slots) - a good corroborating sign for the whole approach.
- **Not yet added to `rom_addresses.py`/`CONFIRMED_COURSE_IDS`** - only got the one new
  data point (Yoshi Falls=18) before the touch regression interrupted a second
  cross-validation sample (Cheep Cheep Beach, mid-attempt when things went sideways).
  Worth cross-checking the `0xE0` Time Trial offset holds for a different track/cup before
  fully trusting it, same as was done for the Grand Prix offset.

### Real generation testing (not just unit tests) found and fixed a genuine overflow bug
With track data collection blocked, switched to a different, entirely emulator-independent
piece of task 8: actually running AP's real `Generate.py` pipeline (not just the
lightweight `WorldTestBase` unit tests) against hand-written test YAMLs. Needed
`SKIP_REQUIREMENTS_UPDATE=1` in the environment to bypass an interactive "install
pkg_resources" prompt that fails non-interactively (newer `setuptools` no longer bundles
`pkg_resources` by default) - otherwise works with the same lightweight dependency set
already in place.

First real test (`combination` goal, `required_cup_count=3`/`required_time_trial_count=4`/
`required_mission_count=6`, both `Randomize Characters` and `Randomize Karts: yes_all` on)
immediately hit: `Player TestPlayer had 24 more items than locations. Unable to place all
items.` - 55 real items generated (12 Characters + 36 Karts + 3 Progressive Cup + 4
Progressive Time Trial) against only 31 actual locations. This is exactly the scenario
`__init__.py`'s own TODO comment had flagged as "not supposed to occur" per Instructions.
txt's assumption - now proven it *can*, for smaller goals combined with both cosmetic-item
categories enabled. Never caught by the unit test suite because none of its option
combinations happened to combine a small goal with both `randomize_characters` and
`randomize_karts: yes_all`.

**Fixed in `__init__.py`'s `create_items()`**: split the pool into `progression_pool`
(Progressive Cup/Time Trial - always included in full, since `rules.py`'s completion
condition depends on holding every copy) and `bonus_pool` (Characters/Karts - only
"Useful", not required for completion). If `len(bonus_names) > bonus_capacity` (remaining
room after progression items), take a random sample down to fit rather than including all
of them - some characters/karts simply won't appear as items in a small-goal seed, which
is an acceptable, expected trade-off for non-required bonus content. Verified against
three configs after the fix: the original overflow case (31 locations, exactly filled, no
crash), a maximal case (`cups_all` + everything randomized - 40 locations, Characters+Karts
correctly trimmed from 48 to fit), and a minimal case (both off, small `cups_count` goal -
10 locations, no trimming needed, filler pads the rest). All three produced real output
zips successfully. Re-ran the unit test suite after the change - still 34/34 passing.

Also manually inspected one generated seed's spoiler log end-to-end: 31/31 locations
filled with sensible-looking items (real character/kart/track/mission names, Progressive
Cup/Time Trial correctly scattered), and the playthrough-sphere analysis was internally
consistent (only progression-item-holding locations appear in the sphere breakdown, which
is exactly right - useful items aren't part of the critical path). First real evidence
this world generates a genuinely playable, correctly-structured seed end-to-end.

### Where things stand
- Emulator: idle at main menu, touch input not responding - needs the user to check
  BizHawk's controller/touch configuration before any more live RAM work can continue.
- `CONFIRMED_COURSE_IDS`: 3 of 32 tracks now known (Figure-8 Circuit=1, Desert Hills=5,
  Yoshi Falls=18) - blocked on the touch regression for more, and the Time Trial offset
  (`0xE0`) still wants one more cross-validation sample before fully trusting it.
- Real generation now confirmed working end-to-end for small/medium/large configs, with a
  genuine bug found and fixed along the way that the unit test suite structurally could
  not have caught (no test combined a small goal with both bonus-item categories).

### More non-emulator cleanup while input stayed blocked
Kept working through remaining TODOs that don't need BizHawk access:
- **Wrote `worlds/mkds/docs/setup_en.md`**, which didn't exist despite `__init__.py`'s
  `WebWorld` already referencing it. Modeled on `marioland2`'s guide but corrected for a
  real structural difference: MKDS has no ROM patch (`client.py`'s `patch_suffix` is a
  placeholder, not a working mechanism) - players load their own ROM directly and connect
  the Lua script + client manually, they never see an "Open Patch" step. Says plainly that
  the world is still under active development (not every track/mission sends checks yet).
- **`base_id` collision check**: imported `AutoWorldRegister` directly and diffed MKDS's
  chosen item/location ID ranges against every world that could actually load in this
  environment (49 of ~90 bundled worlds - the rest fail on missing optional deps like
  `bsdiff4`/`orjson`, unrelated to MKDS). Zero exact collisions found. Not exhaustive (the
  other ~40 bundled worlds, plus anything in a real player's own `custom_worlds` folder,
  aren't covered), but real positive evidence now instead of a pure placeholder guess -
  updated the TODO comments in `items.py`/`locations.py` accordingly.
- **Fixed a real bug in `validate_rom`**: it checked `game_code.startswith("AMC")`, which
  would also accept the EU (`AMCP`) or JP (`AMCJ`) builds - actively wrong, since every
  address in `rom_addresses.py` was verified against the USA build specifically, and EU's
  static layout is already known to be shifted (see `g_GlobalMV`'s notes). Confirmed via
  GBATEK (the authoritative NDS technical reference) that the gamecode field is exactly 4
  bytes at header offset `0x00C`, and cross-checked "AMCE" as MKDS USA's real code against
  GameTDB. Tightened the check to an exact match. The offset itself (`0x0C`) was already
  correct - only the comparison was too permissive.

All three are code/doc changes only, verified with the unit test suite (still 34/34) and
an explicit `py_compile` check on `client.py`.

### Emulator state changed unexpectedly mid-session
Checking back on the touch-input issue, the screenshot showed an ACTIVE RACE instead of
the main menu I'd left it at - state changed without me sending any input. Didn't send
any further scripted input in response (in case the user is at the controls themselves
right now investigating the controller issue) - just noting the observation and moving
on to other non-emulator work rather than risking interference.

### Full cross-file consistency review (via a dedicated read-only subagent pass)
With emulator access still uncertain, ran a thorough read-only review of every file in
`worlds/mkds/` cross-referenced against every other file (location-name string
construction matching between `client.py`/`locations.py`/`rules.py`, `world.required_*`
attributes declared vs. consumed, every `rom_addresses.py`/`items.py`/`locations.py`
constant referenced elsewhere actually existing). Found five real issues, most of the
codebase came back clean:

1. **Real bug, now fixed**: `client.py`'s `_apply_received_items` wrote cup-unlock bits
   for `cup_order[:progressive_cup_count]` - but `rules.py`'s access rule is 0-indexed
   (first required cup needs 0 copies held, see the earlier off-by-one fix). With 0
   copies received, `cup_order[:0]` is empty, so NOTHING gets unlocked yet - fine if the
   randomly-chosen first required cup happens to be one of the 4 vanilla-free starters
   (Mushroom/Flower/Shell/Banana), but a genuine softlock if it's one of the other 4
   (Star/Special/Leaf/Lightning): nothing could unlock it, and the only way to receive
   the first Progressive Cup copy was winning a cup that couldn't be reached without
   already holding it. Fixed by matching the +1 exactly: `cup_order[:progressive_cup_
   count + 1]` - holding N copies now correctly unlocks cups at positions 0..N inclusive.
   This is exactly the kind of gap that only surfaces from tracing rules.py's logic
   through to client.py's actual write behavior, not visible from either file alone -
   good argument for this kind of cross-file review pass periodically.
2. `options.py`'s `RequiredMissionCount.range_end` was still 60, left over from before
   the mission count was confirmed at 63 (7x9, see NOTES.md's mkds-re section) - a real
   functional bug (silently capped player-selectable required_mission_count 3 below the
   actual maximum), not just stale docs. Fixed to 63, removed the now-resolved TODO.
3. `rom_addresses.py`'s Mission Mode comment said "needs updating" about
   `locations.py`'s mission-per-level count, immediately followed a few lines later by a
   note that it was ALREADY updated - leftover phrasing from before the fix, corrected.
4. Unused imports removed: `ClassVar`/`ItemClassification`/`RandomizeCharacters` from
   `__init__.py`, `Region` from `locations.py` (locations use plain region-name strings,
   not `Region` objects - `regions.py` is where actual `Region` objects get created).
5. `ItemData.count` field (`items.py`) was set but never read anywhere - actual pool
   quantities are computed independently in `__init__.py`'s `create_items()`. Removed the
   field and the two now-pointless module-level constants that only existed to feed it
   (`items.py`'s own duplicate `CUPS` list - `locations.py`'s is authoritative and
   already used everywhere else; `TIME_TRIAL_UNLOCK_COUNT`, whose stale "granularity not
   decided" TODO is now superseded by the much more thorough Time Trial investigation in
   `rom_addresses.py`).

Re-verified after all five fixes: unit test suite (34/34), `py_compile` on every file in
the world, and a full real-`Generate.py` run (same `combination` config used to catch the
original item-overflow bug) - all still produce a clean, real output seed.

### Touch input recovered, resumed course_id collection, found and fixed a real reliability gap
Rechecking the emulator later, the screen had changed to an active race without any input
from me - almost certainly the attract-mode demo cycling on its own, not the user at the
controls (confirmed by testing a deliberate button press, which correctly moved a menu
cursor). Scripted input is working again - resumed data collection.

**Two more Time Trial samples, cross-validating the `0xE0` offset**: Cheep Cheep Beach
(`internal_course_id=0`) and, from earlier in this same round, Yoshi Falls (`=18`) - both
with `cup_idx=0` (Mushroom Cup) and clean all-zero CPU driver slots as expected. `CONFIRMED_
COURSE_IDS` is now 4 of 32: `{0: "Cheep Cheep Beach", 1: "Figure-8 Circuit", 5: "Desert
Hills", 18: "Yoshi Falls"}`.

**Found a real reliability gap in the Grand Prix offset while attempting a 5th sample**:
navigation got confused (ended up in an unplanned Grand Prix race instead of the intended
Time Trial) and reading `RACECONFIG_OFFSET_FROM_RACESTATUS` (`0x43F8`) from a valid, stable
`RaceStatus` pointer produced `cup_idx=65536` - clearly not a real `RaceConfig` struct,
confirmed non-transient by re-reading the same address twice with identical results. The
offset that worked cleanly for two earlier Grand Prix races does NOT always hold - exact
cause not confirmed, but the leading hypothesis is that races beyond the first in a 4-race
Grand Prix cup accumulate additional heap allocations (previous race results/transitions)
that shift the gap between `RaceStatus` and `RaceConfig`, since both earlier clean reads
came from a freshly-started first race and this one may not have been.

This mattered more than it might have a session ago: `CONFIRMED_COURSE_IDS` now has a `0`
entry (Cheep Cheep Beach), and the bad read's `course_id` happened to read as `0` too -
meaning without a fix, this failure mode could have caused client.py to send a check for
completely the wrong track. **Fixed** by having `client.py`'s `_read_internal_course_id`
also read `cup_idx` and only trust `course_id` if `cup_idx` is in the real 0-7 range,
returning `None` (already-handled as "nothing to send") otherwise - a cheap, general
sanity gate that doesn't depend on root-causing the exact allocation-order theory. Re-
verified: unit tests (34/34), `py_compile` on `client.py`.

This is a good example of why the "don't send a guessed/wrong location" philosophy
threaded through this whole client.py needs backing up with actual validation, not just
good intentions in comments - the fixed offset alone was not sufficient protection.

### Correction: the Time Trial offset is unreliable - walked back 2 of the 4 course_id entries
Went to collect a 3rd Time Trial data point (Luigi's Mansion, navigating carefully this
time with a screenshot at every step after the earlier confusion) and got
`internal_course_id=0, cup_idx=0` - identical to the earlier Cheep Cheep Beach reading.
Widened the read to check every RaceConfig field (cc_type, race_mode, display_mode,
cpu_mode, player_driver_id, driver 0's character_id AND kart_id) and waited an extra 2
seconds and re-read in case of a population-timing issue - every field read as a clean,
internally-plausible all-zero, identically, both times.

Two different real tracks cannot both genuinely have `internal_course_id=0`. Since
everything about both reads looked locally consistent (nothing as obviously wrong as the
Grand Prix case's `cup_idx=65536`), the likely explanation is the SAME failure shape seen
earlier when hunting for the Grand Prix address in the first place: landing on
`RaceConfigManager.next_race` (the inactive staging copy) instead of `.cur_race`, which
would legitimately read as clean zeros without tripping any single-field sanity check.
This means the `0xE0` Time Trial offset is not reliable, and by extension the *methodology*
of "two internally-consistent-looking samples equals cross-validated" was insufficient -
the earlier "Yoshi Falls=18" reading looked fine on its own merits at the time, but with
Time Trial's offset now known to sometimes land on inactive memory, there's no independent
way to confirm 18 was ever really correct either.

**Removed both Time Trial-derived entries from `CONFIRMED_COURSE_IDS`** (Yoshi Falls,
Cheep Cheep Beach) rather than ship data with newly-uncertain provenance - back to 2 of 32
(Figure-8 Circuit, Desert Hills), both Grand-Prix-derived and multi-field cross-validated
at the time they were captured. `rom_addresses.py` now marks `RACECONFIG_OFFSET_FROM_
RACESTATUS_TIME_TRIAL` as explicitly unreliable, with the reasoning kept in place as a
starting point for whoever investigates this next, not as something to build on.
Client.py's existing `cup_idx`-range sanity check does NOT catch this failure mode (0 is
a valid cup_idx) - noted explicitly so a future safety improvement doesn't assume that
check already covers it.

**Takeaway for future data collection sessions** (Grand Prix or Time Trial): don't trust
two internally-consistent samples as sufficient cross-validation on their own - the
"landed on the wrong-but-plausible-looking struct" failure mode specifically produces
internally-consistent results. Real cross-validation needs either (a) enough independent
samples that a coincidence becomes implausible (the Grand Prix entries had this, from
genuinely different cups/tracks with matching character_id evidence too), or (b) some
field that's verifiably impossible to fake by chance (like the very first Grand Prix
`cup_idx` matches, which had a 1-in-8 chance of being coincidentally right - twice - versus
Time Trial's `cup_idx=0` both times, which had a much higher baseline chance of matching
by coincidence since Mushroom Cup was selected both times).

Emulator rebooted back to a clean idle state afterward.

### Kart-tier flag: not cached anywhere near the unlock-flags word (clean negative result)
Tried a lower-risk investigation while reconsidering whether to keep pushing on course_id
collection: does the "kart tier" derived value (the coarse 4-tier `ExtraKartUnlockState`
progression, needed to make the "yes_unique_only" kart mode fully work) live anywhere near
the already-proven `UNLOCK_FLAGS_ADDRESS`? Used direct memory writes (no menu navigation
needed - toggled `UNLOCK_MASK_DRY_BONES_GROUP` on/off at `UNLOCK_FLAGS_ADDRESS` itself)
combined with NARROWSTART/TOGGLE across the whole 0x800-byte region around it, 3 full
rounds with varied timing. Converged to exactly one surviving candidate, and that one was
trivial (just the upper byte of the write itself - observing my own input, not a
discovery). Conclusion: the tier value isn't cached nearby and doesn't update from a
passive write, consistent with `UNLOCK_FLAGS_ADDRESS` itself only being "read when a menu
screen loads." Finding it for real would need the navigation-based version of this test
(write, navigate to a screen that consults it, then search) - not attempted, given what
happened next.

### The RaceConfig offset reliability problem is worse than it looked - confirmed sensitive to unrelated prior activity
Tried to find `g_RaceConfigManager`'s real static pointer (removing the offset-reliability
risk at its root) by getting a freshly-verified, carefully-screenshot-confirmed race 1
(Mushroom Cup, Figure-8 Circuit) and reading `RACECONFIG_OFFSET_FROM_RACESTATUS` from it -
the exact same "safe" scenario (fresh race 1) that worked cleanly the first two times this
session. This time it read `internal_course_id=4178, cup_idx=4096, race_mode=38` - all
obviously wrong (though `cup_idx`'s range check, already added to `client.py`, does
correctly reject this specific case).

This attempt came immediately after the kart-tier NARROWSTART/TOGGLE test above, which
repeatedly wrote different values to `UNLOCK_FLAGS_ADDRESS`. That's the most likely
explanation: the offset isn't just sensitive to which race-within-a-cup this is (the
earlier hypothesis), it's sensitive to unrelated prior heap-affecting activity in general -
exactly the untested scenario the original caveat already flagged, now empirically
confirmed rather than theoretical. This matters a lot for real play: receiving items
*is* `UNLOCK_FLAGS_ADDRESS` writes, happening throughout a normal session - so the
"fresh boot, nothing written yet" condition the two clean reads actually depended on
will rarely hold once a real multiworld is running.

**Substantially strengthened the caveat in `rom_addresses.py`** to reflect this - it now
says plainly not to treat `CONFIRMED_COURSE_IDS` or the offset mechanism as production-
solid, and that current understanding cannot predict when it will or won't work. Did NOT
attempt the planned wide static-pointer search, since the fresh target needed for it
turned out to be invalid - nothing valid to search for. Left clear instructions for
whoever picks this up next: get a cleanly-verified target FIRST (fresh boot, race 1, zero
prior unlock-flag writes this session) before attempting the static-pointer search again.

**Where this leaves the project**: the DETECTION side of race/mission wins (confirmed
solid all session, no new doubts) is unaffected. The MAPPING side (which specific track a
detected win corresponds to) is real but fragile - it will likely under-deliver (silently
send nothing for a real win) far more often than it mis-delivers (send a wrong check),
which is the right failure direction given the project's stated philosophy, but "silently
does less than it should, unpredictably" is still a real limitation worth being upfront
about rather than presenting the course_id mechanism as more solid than it's actually
proven to be right now.

Emulator rebooted to a clean idle state.

### CRITICAL CORRECTION: the RaceConfig offset mechanism was worse than "fragile" - disabled the sends entirely
Went back for one more attempt at finding `g_RaceConfigManager`'s real static pointer,
starting from the CLEANEST possible conditions: fresh reboot, immediate race 1 (Figure-8
Circuit, screenshot-confirmed), zero other activity beforehand - explicitly designed to
rule out the "contaminated by prior heap activity" theory from the previous section.

Reading `RACECONFIG_OFFSET_FROM_RACESTATUS` gave `internal_course_id=5, cup_idx=0`.
Reading the exact same address again moments later, same race, nothing else happened in
between, gave `internal_course_id=6`. **The value changed between two successive reads of
the same address with nothing in between that should change it.** A full-struct read
right after that showed `display_mode`/`cc_type` in the tens of millions and nonsensical
per-driver data - this address is not landing on a stable struct at all, let alone the
right one.

The genuinely alarming part: `5` is the exact value already sitting in `CONFIRMED_
COURSE_IDS` as "Desert Hills" - and this read happened while actually racing Figure-8
Circuit. If check-sending had been live for this track, this would have sent a check for
completely the wrong location. This isn't a theoretical risk anymore; it happened, live,
in testing. It also retroactively undermines confidence in the original "Figure-8
Circuit=1, Desert Hills=5" readings themselves - if the same offset can land on unstable,
garbage-but-plausible-looking memory under supposedly-identical conditions, there's no
principled reason left to trust that the ORIGINAL two reads weren't also coincidental
pattern matches in noisy memory rather than genuine, correct struct reads.

**Disabled the check-sending code paths entirely** rather than leave this live:
- `client.py`'s `_check_race_result`: the course_id lookup/send block is now commented
  out. Detection (the `race_ended` + genuine-permutation check above it) is untouched and
  stays solid - only the "map the win to a specific track and send" step is disabled.
- `_check_mission_result`: same treatment for the mission-level/stage lookup/send block,
  which depended on the identical unreliable offset. The win-flag detection itself is
  unaffected.
- Updated the module docstring to state plainly that sending is implemented but
  deliberately disabled, and why - re-enabling is a one-line uncomment in each method once
  `RaceConfig` has a real, trustworthy address (not before).
- Kept the now-unused-except-in-comments imports (`location_table`,
  `MISSION_OBJECTIVES_BY_LEVEL`) with an explanatory comment rather than removing them, so
  re-enabling doesn't also require restoring imports.

Re-verified: unit tests (34/34), `py_compile` on `client.py`.

**Where this actually leaves the project**: detection of race wins and mission wins is
real, solid, and unaffected by any of this - that part of the mechanism was never in
doubt. What's now honestly unresolved is turning a detected win into the correct
LocationChecks message - RaceConfig's live address needs to be found properly (the real
`g_RaceConfigManager` static pointer) before that can be trusted again. Everything else
built this session (unlock-flag item application, the full rules.py/regions.py goal
logic, the item-pool overflow fix, the cup-unlock bootstrap fix, real generation testing)
is unaffected and remains solid - this correction is scoped specifically to "which
track/mission did a detected win happen on", nothing else.

Stopping live RAM investigation here for this session. This is a better place to leave
things than continuing to accumulate more data points on a mechanism just shown to be
untrustworthy even under ideal conditions - the honest, corrected state (detection solid,
mapping real-but-disabled-pending-a-proper-fix, clear reasoning recorded) is worth more
than either silently shipping the risk or spending more time guessing at offsets that
have now failed under every condition tried.

---

## Session 2026-08-04 (later still): EU unlock-flags confirmed, course-id table found, client.py re-enabled

Picked up right after the EU pivot (region switch to AMCP, `RACECONFIGMANAGER_ADDRESS`
resolved via mkds-re's direct static pointer - see rom_addresses.py for that story). Two
gaps remained: `UNLOCK_FLAGS_ADDRESS` was still an unverified USA holdover, and
`CONFIRMED_COURSE_IDS` only had 2 of 32 tracks. Both fully resolved this session, plus
`client.py`'s check-sending (disabled during the reliability-crisis correction above) is
back on - for real this time, on a mechanism actually proven trustworthy.

### UNLOCK_FLAGS_ADDRESS confirmed identical on EU - with a real methodology trap found
Hypothesis: `g_SaveDataHolder` (EU `0x0217AA08`) dereferences to `0x023CE270`, and
`+0x70` from that lands exactly on `0x023CE2E0` - the same absolute address already used
for USA. Tested by writing `UNLOCK_MASK_EVERYTHING` there, then **REBOOT**, then
screenshotting Character Select: showed only the untouched 8-starter baseline - looked
like a clean refutation.

It wasn't. Retested the identical write **without** an intervening reboot (back out of
Character Select and back in instead, to force the same "read on screen load" behavior
documented earlier) - immediately showed the full expected effect: bonus characters,
kart counter at "1/36", all 8 cups on Cup Select. Root cause: `client.reboot_core()`
reloads RAM from the last **saved** `.sav` state, not from live pre-reboot RAM - it
silently discarded the write before the screenshot ever happened. The address hypothesis
was right the whole time; the first test's own methodology was the thing that was wrong.
**Lesson for future write-tests: never REBOOT between a write and its verification
unless the write is also expected to survive a save reload - they test different
things**, and a reboot-based "refutation" of an otherwise-sound hypothesis deserves a
no-reboot retest before being trusted.

`UNLOCK_FLAGS_ADDRESS` is now marked confirmed-for-EU in rom_addresses.py. This also
means the entire USA-era bit map (all the individually-isolated character/cup bits) was
carried over completely unchanged - none of that granular bisection work needed redoing.

### probe.lua bug found and fixed: `tonumber(s, 16)` rejects a `"0x"` prefix
Sent a `READAT` macro command using `0x`-prefixed hex addresses (`READAT 0x021759C0 ...`)
- every prior command all session had omitted the prefix, by convention rather than
necessity, so this was the first time it got tested. Lua's `tonumber(s, 16)` does NOT
strip a `"0x"` prefix once a base is passed explicitly (that auto-detection only applies
when base is omitted) - it silently returns `nil`, which then fed `nil` into
`memory.read_bytes_as_array` and killed the script's whole frame loop with an uncaught
error. Symptom was a fully unresponsive probe (trigger files sat unconsumed) with the
game itself still running fine underneath - only the automation layer had died.

**Fixed properly, not worked around**: added a `parse_hex()` helper to probe.lua that
strips an optional `0x`/`0X` prefix before calling `tonumber(s, 16)`, and swapped every
hex-parsing call site (`READAT`, `FINDBYTES`, `SCANSTART`, `NARROWSTART`, and the
`write_trigger.txt` handler) over to it - so this class of mistake can't recur regardless
of whether future commands include the prefix or not. Required one user-assisted script
reload (Tools > Lua Console > reload) to take effect; game state itself was undisturbed
by the crash (confirmed: the live `RaceConfigManager` pointer read identically before and
after).

### Time Trial course_id: confirmed does NOT live-update from menu cursor movement
Open question from earlier: does `RaceConfig.internal_course_id` update as you browse
menus, or only once a race is actually active? Tested directly on Time Trial's per-track
select screen (one level deeper than Grand Prix's cup-only preview - GP has no
individual track selection at all, it always plays a cup's 4 tracks in fixed order
starting from track 1, which is why an earlier cursor test on the GP cup screen never
saw the value change). Result: cursoring from Figure-8 Circuit to Yoshi Falls visibly
changed the on-screen highlight but `course_id` stayed at `20` (Figure-8) throughout -
confirms `RaceConfigManager.cur_race` only reflects the actually-loaded race, not
whatever the menu cursor is previewing (almost certainly `next_race`, the struct's other
half, is what's live during menu browsing instead). Doesn't block anything - detection
already only ever reads this after `race_ended` is confirmed true, i.e. well after an
actual race, so this was a methodology question, not a live bug.

### CONFIRMED_COURSE_IDS completed for all 32 tracks - not by racing each one
Was about to bulk-collect course_ids by actually running all 32 tracks (now that
everything's unlocked, no need to win cups first) when a better source turned up:
`reference/mkds-re/tools/save-editor/source/main.cpp` has a `g_CourseNames[]` array
(save-slot/UI order, 32 entries) that turned out to be a DIFFERENT numbering scheme than
`RaceConfig.internal_course_id` - useful for cross-checking track identity, not directly
usable as the runtime id. The real find was `mkds-eu-types.h`'s `InternalCourseId` enum
(0-54, includes non-race entries - battle stages, cut content, staff roll) alongside a
separate compact `CourseId` enum (0-31, matches the UI/save order exactly) - and,
critically, `mkds-eu.h` declaring `g_InternalCourseIdOrderedTable[32]` at EU address
`0x02154128`: the game's own `CourseId -> InternalCourseId` lookup table, living in
static ROM data (no dereferencing, no heap, always readable).

Read it live with one `READAT`. Cross-validated three independent ways, all agreeing on
every single one of the 32 entries: (1) each table value matches its expected codename in
the `InternalCourseId` enum (e.g. table[0]=20, and id 20 is literally named
`cross_course` - "cross" for a figure-8's crossed shape), (2) table[0]=20 and table[4]=27
exactly match the two values already independently confirmed by actually racing
(Figure-8, Desert Hills), (3) `CourseId`'s enum names, in order, match
`locations.py`'s web-sourced `TRACKS_BY_CUP` flattened order name-for-name - two
independently-derived sources (one from decompiled source, one from web research)
agreeing completely. `rom_addresses.CONFIRMED_COURSE_IDS` now has all 32 tracks mapped,
each at the same confidence level the original 2 empirically-raced entries had.

### client.py: check-sending re-enabled
With `RACECONFIGMANAGER_ADDRESS` proven reliable (see the EU-pivot section above) and
`CONFIRMED_COURSE_IDS` now complete, uncommented the send paths in `_check_race_result`
and `_check_mission_result` that were disabled during the reliability-crisis correction.
Rewrote `_read_internal_course_id` to dereference `RACECONFIGMANAGER_ADDRESS` directly
(with a `HEAP_RANGE` plausibility check, mirroring the existing `GLOBAL_MV_POINTER_
ADDRESS` pattern) instead of the abandoned `RACECONFIG_OFFSET_FROM_RACESTATUS` empirical
offset; factored the "dereference RaceConfigManager, sanity-check it's heap-range" logic
into a shared `_read_race_config_base` helper used by both the course-id and
mission-level/stage reads, avoiding duplication. Re-synced into
`reference/Archipelago/worlds/mkds/`, re-ran the full test suite (34/34 still passing)
and an explicit `client.py` import check (loads clean, no mkds-specific errors - only the
usual unrelated other-world missing-optional-dependency noise already established as
expected).

**Where this actually leaves the project**: race-win and mission-win detection AND
mapping-to-location-and-sending are both live and, as far as static analysis plus live
spot-checks can establish, trustworthy - the reliability crisis that forced disabling
this same code path earlier was specific to the abandoned USA empirical-offset
mechanism, which no longer exists in the codebase at all. Remaining known gaps (all
pre-existing, not new): kart items are received but not applied (needs the
starting-kart-assignment patch mechanism), Time Trial has no location/goal wiring yet,
and mission rank ("3 Stars") isn't read yet (only "Clear"). Next natural milestone is
task 8 - package, generate a real test seed, and playtest end-to-end against an actual
AP server.

### Gap found while planning the end-to-end playtest: no cup-win detection, no CLIENT_GOAL at all
Before actually attempting task 8, checked what a real playthrough would need to
exercise. Found two things that had never been implemented, not just disabled: (1)
`client.py` only ever sent "{track} - 1st Place" checks - there was no code path for
"{cup} - Win" at all, even though rules.py's completion_condition (and the DEFAULT goal,
`cups_all`) requires it; (2) `ClientStatus.CLIENT_GOAL` was never sent anywhere in the
file - a perfect playthrough would rack up individual checks forever and never actually
finish the seed. Neither is a regression from the reliability-crisis correction earlier
in this file - these paths simply never existed.

**Why "cup win" needs its own detection, separate from race wins**: Grand Prix scores a
cup as a 4-race points total, not "did you win every race" - you can win the cup without
winning every individual race, or lose it despite winning the last one. `RaceStatus`
(already fully mapped) has nothing cup-level in it; needed a different structure.

**Found it via the same mkds-re research approach used all session**: `enum CupResult`
(Gold/Silver/Bronze/Lost) led to `g_RacerPositionToCupResultTable[8]` (EU
`0x02154064`, static ROM data - converts a 0-7 overall standing into the actual trophy,
rather than assuming "rank 0-2 = podium"), which led to `struct StructTrophyResult`
(`cup_idx` at 0x0, `player_global_rank` at 0x2) and its owning static pointer
`g_GlobalTrophyResult` (EU `0x0217B200`) - same naming/pointer convention as the
already-verified `g_GlobalMV`/`g_RaceConfigManager`, presumably populated when the
post-cup trophy ceremony screen shows. Read as null (`00 00 00 00`) while sitting in
ordinary menus - consistent with the "populated only during the ceremony" hypothesis,
but that's a weak signal, not proof; unlike everything else confirmed this session, this
one hasn't been checked against a real completed cup yet. Implemented `_check_cup_result`
in `client.py` following it (same heap-range/plausibility-check pattern as every other
pointer-chase in this file), clearly marked research-based-pending-live-verification in
both files (matching the precedent already set by `DRIVERSTATUS_FLAG_MISSION_WIN_DELAY`).

**CLIENT_GOAL**: rather than track completion separately per-category, `_check_goal_
complete` reconstructs the exact same required-location-name set `rules.py`'s
`decide_goal_requirements` computes at generation time (same formula, fed from the four
lists already in `slot_data`), and compares it against `ctx.checked_locations` - the
framework's own server-confirmed state, not a client-local guess. This means it's
automatically correct (no further changes needed here) once the two remaining detection
gaps close: mission goals need "- 3 Stars" (mission `rank` field, address not found yet)
in addition to "- Clear" (already sent), and Time Trial goals need "- Staff Ghost Beaten"
(no detection at all yet). Cup-only goals - `cups_all`/`cups_count`, the default - are
the one category that can reach CLIENT_GOAL for real today, once cup-win detection above
is confirmed live.

Re-synced to `reference/Archipelago/worlds/mkds/`, re-ran the full suite (34/34) and an
explicit `client.py` import check (clean, only the usual unrelated-world dependency
noise) after each change in this section.

**What's left before task 8's end-to-end playtest is meaningful**: live-verify
`g_GlobalTrophyResult`/`_check_cup_result` against an actually-completed cup - the one
piece in this session's work that's implemented from research alone with no live signal
yet. Automating a full 4-race Grand Prix via blind scripted input (no steering feedback
loop built for actual driving, unlike the menu-navigation macros used all session) would
be a much larger, more error-prone undertaking than anything attempted so far - flagging
this to the user as a good candidate for them to play through by hand instead, same as
the earlier Kart Select OK-button case where direct human input was faster and more
reliable than continued blind automation.

### Cup-win detection: CONFIRMED LIVE (user played a real cup)
User agreed to play through a Grand Prix cup by hand. Hit an unrelated environment snag
along the way: BizHawk's whole window (not just the game) froze on every press of their
controller's L1, even after removing every hotkey/control binding from that button in
BizHawk's own config - ruled out both a BizHawk hotkey conflict and a game-control
mapping issue, points at something lower-level (controller driver/OS, or a genuine
BizHawk/melonDS-core input bug) that's still unresolved but is a separate, non-blocking
issue - avoiding L1 (no drift-boosting) was enough to finish the race normally.

Reached the trophy screen after Mushroom Cup, 150cc, with a real 1st-place/gold result.
Read `g_GlobalTrophyResult` (`0x0217B200`) immediately: `0x02389040` - a genuine
heap-range pointer, non-null. Dereferenced and read the struct: `cup_idx=0` (matches
"MUSHROOM CUP" on screen exactly - cup 0 in `locations.CUPS` order), `player_global_
rank=0` (matches the "1st" badge on screen exactly). Read `g_RacerPositionToCupResult
Table[8]` live too: `00 01 02 03 03 03 03 03` - confirms the table isn't a naive
"top-3=podium" assumption baked into the code, it's read from the real game data, and
`table[0]=0=Gold` matches the gold trophy visible on screen. Every single field checked
against what was actually on screen, not just "looked plausible" - the same bar every
other confirmed address in this file has been held to.

`rom_addresses.py` and `client.py` both updated from "research-based, pending
verification" to confirmed. Full test suite re-run clean (34/34) after each doc update.
This closes the cup-win detection gap entirely - `_check_cup_result` and `_check_goal_
complete` are both now fully trustworthy for cup-based goals (`cups_all`/`cups_count`,
the default goal type). Remaining gaps for the OTHER goal types are unchanged and
already well-documented: mission goals need "3 Stars" rank detection (address not found
yet), Time Trial goals need staff-ghost-beaten detection (not started).

The L1 freeze is still open and worth a fresh look if it recurs - next diagnostic step
would be checking whether a keyboard-bound key reproduces it (isolates controller/driver
vs. BizHawk/core), and whether it happens with the Lua console fully closed (rules out
probe.lua, though nothing in the script special-cases any button - PRESS just calls
`joypad.set` generically, same code path for every button name).

### Task 8 started: packaged as a real .apworld, generation verified, user setting up live test
User offered to set up the actual server+client+BizHawk connection themselves (task 8's
end-to-end playtest) rather than have this continue as blind automation - sensible, since
the earlier trophy-screen test already showed real gameplay is much faster by hand.
Before handing off, did the packaging/generation side directly:

**Packaged `mkds.apworld`** (`F:\Mario Kart DS AP\mkds.apworld`) - a zip of `worlds/mkds/`
with an `archipelago.json` manifest at the zip root (`game`, `compatible_version`/
`version`, `world_version`). Manifest format confirmed by reading `worlds/Files.py`'s
`APContainer`/`APWorldContainer` directly rather than guessing - `compatible_version`
must be `<=` the loading AP instance's own container version (7 in this 0.6.8 reference
checkout). Checked the frozen distribution's actual version via its .exe's embedded
`FileVersion` (PowerShell `Get-Item ... | VersionInfo`) rather than assuming: 0.6.7, one
patch behind this checkout - close enough that the container format should match.

**Verified the packaging for real**, not just "the zip looks right": temporarily moved
the loose-folder `worlds/mkds` fully OUT of the checkout (renaming in place isn't enough
- the loader matches by the `game` class attribute, not folder name, so a renamed loose
folder still collides with and silently wins over the zip), dropped `mkds.apworld` into
a `custom_worlds/` folder, and confirmed `AutoWorldRegister.world_types['Mario Kart DS']`
resolves to `worlds.mkds.MKDSWorld` (loaded from the zip this time) with `world_version`
correctly parsed as `0.1.0` from the manifest. Hit and fixed one real environment gap
along the way: `worlds/Files.py` imports `bsdiff4` unconditionally, so the ENTIRE
apworld-zip-loading path was untestable until `pip install bsdiff4` (clean prebuilt
wheel, no compiler needed) - not a packaging bug, just a dependency this lightweight test
environment never needed until now. Restored the loose folder afterward for normal dev
workflow.

**Wrote and verified `mkds_test.yaml`** (2-cup `cups_count` goal, everything else off,
for a fast first test) by actually running it through `Generate.py` - not just eyeballing
the YAML. Real output produced (`AP_....zip`), spoiler log confirms the option values
round-tripped correctly and the fill/playthrough solver found a genuinely logical,
2-sphere-solvable path (sphere 0: nothing needed - one of the free first cup's own
tracks already holds the Progressive Cup that unlocks the second cup; sphere 1: the
second cup's own win location, now reachable). This is AP's own core solver validating
the seed, not something hand-checked.

**Also fixed `docs/setup_en.md`** - still said "USA ROM" (stale from before the EU
pivot) and understated current status (still said "not every track confirmed" - all 32
are now, plus cup-win/goal-completion work fully today). Both corrected.

Handed off `mkds.apworld` + `mkds_test.yaml` to the user for the real
generate-server-BizHawk-client connection test, since that's squarely in "faster for a
human" territory (GUI app launching, real-time play) rather than something worth
continuing to script blindly.

---

## Session 2026-08-04 (later still): real playtest feedback - one bug fixed, item naming redesigned, and a much bigger unlock-state gap surfaced

The user actually completed a real seed against the real AP server/client (their own
setup, as offered). Real feedback, in order:

1. **Beating a cup sent no check** (individual race wins DID send correctly).
2. **Item should say "Mushroom Cup", not "Progressive Cup".**
3. **Non-required cups were freely playable - only unlocked content should be.** Same
   requirement stated for missions/Time Trial/karts/characters, forward-looking.
4. **No completion message when the 2-cup goal was actually finished** (a direct
   consequence of #1 - if the cup-win check never sends, `_check_goal_complete`'s
   `required_location_ids <= ctx.checked_locations` check can never be satisfied).
5. Follow-up clarification: **at the start of a new game, only 1 character, 1 kart, 1
   cup, and 3 missions should be available** - not vanilla's much more generous
   defaults (8 characters, 2 karts per character, 4 free cups).

### #1 fixed: HEAP_RANGE was the wrong validity check for the trophy pointer
Root-caused by re-reading `_check_cup_result` line by line against the confirmed
`watcher_timeout = 0.5` polling interval (worlds/_bizhawk/context.py) - the trophy
ceremony is shown for several real seconds, so "missed a brief window" doesn't explain a
clean, total non-fire across many poll attempts; a *consistent* rejection does. The
method gated `GLOBAL_TROPHY_RESULT_POINTER_ADDRESS`'s dereferenced value on the same
`HEAP_RANGE` bounds already proven for `GLOBAL_MV_POINTER_ADDRESS` - but that bound was
never independently verified for THIS pointer's target, only extrapolated from the
single sample taken during my own manual verification test. A real playthrough's
different navigation history plausibly allocates the trophy struct somewhere
`HEAP_RANGE` doesn't cover. Fixed by checking only `trophy_ptr == 0` (solidly confirmed
as the real "no ceremony" signature) instead of a range - the `cup_idx`/`player_global_
rank` plausibility check right after remains the real data-validity gate. Not yet
re-verified against a second live cup completion - flagged honestly in both `client.py`
and `rom_addresses.py` rather than claimed as more confident than a single
fix-without-a-retest earns.

### #2 fixed: replaced generic "Progressive Cup"/"Progressive Time Trial" with directly-named items
Worked through the design carefully before touching code, since the naive fix ("just
rename the item") runs into a real tension: can an item be named exactly after what it
unlocks AND still enforce that required cups unlock in a strict left-to-right sequence?
Concluded no - and, more importantly, realized the OLD counted-item system never
actually guaranteed strict sequential play-through either (every "Progressive Cup" copy
was identical/interchangeable, so the fill algorithm could place several or all of them
within the very first required cup's own reachable locations, letting a player jump
straight to a late position without ever touching the ones in between). Given the old
design's real guarantee was never more than "a solvable, well-defined access hierarchy
with a free first entry point," switching to items named directly after their own cup/
track (position 0 free, every other position gated on receiving ITS OWN item) preserves
that exact guarantee while finally letting the received-item name say what it does.

Implemented across all four files that touched the old design:
- `items.py`: `CUPS`/`TRACKS` (imported from `locations.py`) each get a full item-table
  entry; `CHARACTERS` trimmed from all 12 to just the 4 genuinely-lockable ones (see #3
  below - the 8 starters never had a bit to write, so an item for them did nothing).
- `__init__.py`'s `create_items()`: creates one item per required cup/track, skipping
  index 0 (`required_cups_in_order[1:]`, same for time trials) - no item exists for what
  needs none.
- `rules.py`: new `_sequence_access_rule(sequence, position, player)` helper - position 0
  unconditionally `True`, everything else gated on `state.has(sequence[position], player)`
  (its own name, not a predecessor chain or a count).
- `client.py`'s `_apply_received_items`: mirrors the same logic exactly - index 0 always
  unlocked (bootstrap), every other required cup unlocked once ITS OWN named item has
  been received.
- `test/__init__.py`: fully rewritten - `get_items_by_name("Progressive Cup")` no longer
  resolves to anything (the name doesn't exist anymore); tests now pull the real
  per-seed names via `self.world.required_cups_in_order[1:]` /
  `required_time_trials_in_order[1:]` and verify the same "all-but-one held -> not
  beatable, last one added -> beatable" shape, now because each held item independently
  unlocks only its own cup rather than via count/position semantics.

Verified with both the unit suite (34/34, all green after the rewrite) and a real
`Generate.py` run - spoiler log shows `"Delfino Square - 1st Place: Special Cup"`
directly (not "Progressive Cup"), and the playthrough solver still finds a clean,
2-sphere-solvable path confirming nothing about solvability regressed.

### #3/#5: the big one - vanilla's generous defaults can't currently be suppressed
The user's requirement is unambiguous: a new game should start with exactly 1 character,
1 kart, 1 cup, and 3 missions available - everything else AP-gated, full stop. This is a
MUCH stronger requirement than anything solved so far. Every empirical finding from the
original bit-bisection session (`rom_addresses.py`, `CHARACTER_UNLOCK_BITS`/
`CUP_UNLOCK_MASKS`) was about finding bits that ADD access on top of a baseline - that
baseline itself (8 starter characters, each character's first 2 karts, Mushroom/Flower/
Shell/Banana cups) was never found to be gated by ANY bit in `UNLOCK_FLAGS_ADDRESS` or
anywhere else looked at. That's a real, previously-out-of-scope question (nobody had
asked "can the *default* access be turned off?", only "how do you turn *more* on?") -
not something to assume impossible without actually looking. Next step: a fresh,
specifically-aimed investigation (same NARROWSTART/TOGGLE toolkit, new target) before
concluding whether this needs an ASM-level patch or has a RAM-level answer after all.
Repackaged `mkds.apworld` (world_version bumped 0.1.0 -> 0.2.0) with fixes #1/#2 already
included; #3/#5 still open.

### ASM patch investigation - substantial progress, patch point not yet found
User chose to pursue an actual ASM-level patch to suppress vanilla's baseline access
(8 starter characters, each character's first 2 karts, 4 free cups). Checked toolchain
availability first: `devkitARM`/`NCPatcher`/`editwl-bin` (what mkds-re's own
`asmhack-examples` documents using) are not installed and would need real setup; no
disassembler was available either. Searched for prior community work on this exact
problem (none found) before committing to original reverse-engineering effort.

**Built real, working tooling from scratch** (now saved permanently at
`reference/asm_tools/`, not left in the ephemeral scratchpad):
- `pip install capstone` - a lightweight, pure-library ARM/THUMB disassembler. No
  devkitPro/NCPatcher needed for READING code, only for eventually building+injecting an
  actual patch (a separate, not-yet-reached step).
- Discovered the ARM9 binary and overlay files are compressed (Nintendo's "LZ-Overlay"/
  BLZ backward-LZ scheme - confirmed via `asmhack-examples/arm9.json`'s `"compress":
  true"`) - raw extraction produced garbage/invalid disassembly until this was found and
  handled. Rather than guess the format from memory (this project's established
  discipline for anything precision-sensitive), fetched the actual reference
  implementation (`Barubary/dsdecmp`, the original/canonical NDS decompression tool,
  `CSharp/DSDecmp/Formats/LZOvl.cs`) via GitHub's raw content API and ported it line by
  line to Python (`mkds_disasm.lzovl_decompress`). Verified 3 separate times - main
  ARM9's decompressed size matched its own header-derived expectation, and both overlay
  0 and overlay 1's decompressed sizes exactly matched the ROM's own declared
  `ram_size` field for each - strong, independent confirmation the port is correct.
- Parsed the NDS overlay table (header 0x50/0x54) and FAT (header 0x48/0x4C) to find,
  extract, and decompress the 4 ARM9 overlays - menu/scene code lives here, not the main
  binary (confirmed: none of `GetCurrentCharacterUnlockSecretFlags`'s own sub-calls
  resolved to anything in the main binary).
- Built a *resilient* linear disassembly scanner (`resilient_scan_for_calls`) - capstone's
  default `disasm()` generator silently STOPS at the first undecodable instruction, which
  is fatal for scanning a real binary mixing ARM/THUMB code with embedded data/padding. A
  first attempt used a hand-derived byte-pattern prefilter for BL/BLX opcodes instead,
  which worked for ARM but was never independently validated for THUMB and could have
  been silently wrong; replaced it with a version that resyncs to the next aligned
  position after any decode failure, validated by confirming it independently finds a
  call already known to exist from manual disassembly.

**Confirmed via this tooling**: the game's unlock-check mechanism is
`CheckSavedSecretFlag_from_thumb` (EU `0x02056DEC`), taking a single bit-index parameter.
Found 10 live call sites, all in overlay 1 (`0x021804E0`-`0x021A99E0`, confirmed via
embedded asset-filename strings like `"common/select_cup_course_ta_m.bncl"` and
`"gp/select_engine_m.bncl"` to be the real menu/select-screen overlay) - one passing `12`,
eight passing `16`. These EXACTLY match `UNLOCK_BIT_LIGHTNING_CUP` (bit 12) and
`UNLOCK_BIT_MIRROR_MODE` (bit 16) from this project's own earlier empirical RAM
bit-mapping - independent, code-level cross-validation of that entire investigation via a
completely different method (static disassembly vs. live memory read/write testing),
found by accident while looking for something else. Genuinely valuable regardless of how
the rest of this goes.

**Not yet found, despite real effort from multiple angles**: any call checking the other
7 lockable bits (Star/Special/Leaf cups, Dry Bones, Daisy, Waluigi, R.O.B.), or the
character-select/cup-select grid-population logic specifically. Tried: scanning all 4
overlays + main binary for calls to every known secret-flag-check function variant
(`CheckSecretFlag`, `CheckSecretFlagWith_from_thumb`, `HasSomeSecretFlag`, the
`GetCurrent*UnlockSecretFlags` family) - nothing beyond the 10 calls above. Searched
overlay 0 and 1's embedded strings for character-select-related asset names (full
character names, and the 2-letter codes items.py's kart names already use - MR/LG/WR/BW/
DB/DS/WL/RB/PC/YS/TD) - found extensive, clearly-relevant strings for cup/course select,
time trial ghost select, class("engine")/battle-stage/option select, but NOTHING
character-select-specific in either overlay. This is a genuine open question, not
confirmed either way: could mean character-select logic is inlined (direct bit-test
against the loaded flags word, never calling a separate function - which would explain
why a "find calls to X" search comes up empty regardless of how thorough), could mean
it's in a part of the codebase not yet examined by any method tried.

Tangential finding worth a separate look sometime: `mkds-eu-types.h`'s `CharacterId` enum
has `CharacterId_Count = 13`, not 12 - `CharacterId_Heyho_ShyGuy = 12` is a 13th character
never encountered anywhere in this project's testing. Not investigated further (out of
scope for the unlock question), but noted rather than silently ignored.

**Where this leaves things**: real, substantial, verifiable progress (a working
from-scratch decompressor and overlay-extraction pipeline, independent confirmation of
the whole empirical bit map), but the specific patch point for suppressing baseline
access has not been located despite trying every avenue that occurred across two rounds
of investigation (the user chose to continue once after an initial pause checkpoint).
All tooling saved at `reference/asm_tools/mkds_disasm.py` (+ `find_overlay.py`) for a
future session to pick up from without repeating the compression/overlay groundwork -
the module docstring there has the same findings in more technical/reusable form,
including the specific "inline bit-test" next-step idea that hasn't been tried yet.

### Session continues: expanded requirements, real tooling breakthroughs, a better strategy
User clarified the requirement is bigger than first scoped: not just "suppress baseline
access" but ALSO "standard unlock methods need to be removed so that things can only be
unlocked through archipelago" - i.e. even the 9 genuinely-flagged items (Star/Special/
Leaf/Lightning cups, Mirror, Dry Bones, Daisy, Waluigi, R.O.B.) must stop being
unlockable via normal vanilla play, not just have their READ-side gate respected. Firm
directive to get this actually working via a patch file, matching how "almost all DS
games in Archipelago" ship. User is setting up devkitARM (CMake still extracting) and
trying to source NCPatcher + `editwl-bin` in parallel with continued research on this
end - found `editwl-bin` is part of `XorTroll/editwl` (same author as mkds-re).

**Two real tooling breakthroughs this stretch, both before any ASM-writing began:**

1. **Live memory watchpoints, not just static disassembly.** Confirmed via BizHawk's own
   source (cloned locally to `reference/bizhawk_src/`, sparse-checkout of the relevant
   folders only) that melonDS implements `IDebuggable.MemoryCallbacks` on the "ARM9
   System Bus" scope (`MelonDS.IDebuggable.cs`) and that the Lua-facing API is `event.
   on_bus_write`/`on_bus_read`/`on_bus_exec` (`EventsLuaLibrary.cs`) - NOT documented
   anywhere in probe.lua's existing command set because it was never needed until now.
   Added `WATCHWRITE`/`WATCHREAD`/`WATCHDUMP`/`WATCHCLEAR` macro commands to probe.lua -
   these register a REAL hardware watchpoint that fires on every read/write to a given
   address and records frame/PC/LR (via `emu.getregister("ARM9 r15"/"r14")`), persisting
   across many frames until explicitly cleared (unlike everything else in probe.lua,
   which is one-shot per macro call). This is a fundamentally more powerful tool than
   continued static "find calls to X" scanning - it lets the GAME ITSELF reveal which
   instruction touches an address, live, including inlined bit-tests that no static
   call-search could ever catch. One catch found in BizHawk's source: `EnableJIT` must
   be off in the NDS core's sync settings or `MemoryCallbacks` throws `NotImplementedException`
   - not yet confirmed whether this project's BizHawk instance has JIT on or off.
   Also discovered while researching this: BizHawk's Lua Console has a genuine
   auto-reload-on-file-change feature (`Settings.ReloadOnScriptFileChange`, a checkbox at
   Lua Console > Settings > "Reload When Script File Changes") - the user enabled this,
   so probe.lua can now be iterated on for the rest of the session without needing a
   manual reload each time (a real, recurring friction point all session up to this
   point). Script reloaded and the new commands confirmed alive.

2. **A complete, real reference implementation for the AP-side patch delivery.** The user
   provided both their own applied Pokemon Platinum AP patch file (`.applatinum`, a real
   zip container) and, more usefully, `pokemon_platinum.apworld`'s actual `rom.py` source
   (saved locally at `reference/asm_tools/pokemon_platinum_reference/`). This is the
   complete, proven pattern to follow, not just a structural guess:
   - `PokemonPlatinumPatch(APAutoPatchInterface)` (`worlds.Files`) ships pre-built,
     STATIC `bsdiff4` deltas (one per supported ROM revision, picked at apply-time by
     checking a version byte in the user's own ROM) as part of the .apworld package -
     these deltas are built ONCE (via the real devkitARM/NCPatcher toolchain, offline,
     not at generation time) and contain the actual ASM-hack CODE changes.
   - **The clever part**: the ASM-hack's own C source reserves a small, fixed-size data
     buffer, pre-filled at BUILD time with a distinctive, easy-to-find marker string
     (`"AP BIN FILLER " * 5`). After applying the static bsdiff4 delta at patch-apply
     time, the Python-side code searches the patched ROM bytes for this marker and
     overwrites it with freshly-generated, PER-SEED binary data (`ap.bin` - built in
     `generate_output()`, called at AP generation time, packing options/item-placement
     tables as a custom compact binary format the ASM-hack's C code reads directly at
     boot). This is exactly the mechanism needed to get per-seed AP data into a
     statically-compiled patch without recompiling per seed.
   - `generate_output()` is the direct analog of this project's `fill_slot_data()`/
     `create_items()` - it runs once per generation and produces the final `.applatinum`
     output file (manifest + static deltas + fresh ap.bin), via `patch.write(...)`.

**Key strategic realization from studying this**: chasing down and neutralizing the
game's own vanilla "write an unlock bit on winning enough races" trigger (the literal
write-side, which extensive watchpoint/disassembly work would be needed to even locate)
may not actually be necessary. If the ASM-hack instead repoints the character-select/
cup-select/kart-availability/mission-availability READ-side checks to consult a NEW flags
source that the patch itself introduces (e.g. a small buffer living in freshly-claimed
space, following the same "marker string, found and filled at apply-time" trick Pokemon
Platinum uses) - and `client.py` is the ONLY thing that ever writes to THAT new source -
then the OLD save-data SecretFlags mechanism becomes irrelevant to selectability
entirely. Whatever the vanilla game still does to that old flags word (if anything)
stops mattering, because nothing reads it anymore for the purpose of deciding what's
selectable. This turns two hard problems (find-and-neutralize the write-side trigger,
find-and-patch the read-side check for content that currently has NO check at all) into
one: find and repoint the read-side checks, which is work already partially done (the
character/cup-select overlay is identified, even though the exact check instructions
within it aren't yet).

**Not yet done**: actually using the new watchpoint capability (the immediate next
concrete step - watch `UNLOCK_FLAGS_ADDRESS` for both reads and writes while navigating
to/through character select, cup select, and normal gameplay, to finally get a live,
authoritative answer instead of continued static guessing). Toolchain (devkitARM/
NCPatcher/editwl-bin) still not fully ready on either end, so no ASM code has been
written yet - this stretch was entirely about building better tools and understanding
the right architecture before writing any patch code, consistent with this project's
established discipline of understanding before acting.

### Watchpoint testing: a real, surprising result, then a real self-inflicted incident
Used `WATCHWRITE`/`WATCHREAD` on `UNLOCK_FLAGS_ADDRESS` continuously through an entire
navigation: quit an active race -> title -> Time Trials -> character select. Confirmed
via screenshot that character select was showing the plain 8-starter baseline throughout
(matching a clean/unwritten flags word) - **zero write hits, as expected**, but also
**zero READ hits**, which was not expected at all (something has to read this address to
know NOT to show Daisy/Waluigi/R.O.B./Dry Bones).

Sanity-checked the mechanism properly before trusting that null result: first tried
writing to the SAME address via `write_trigger.txt` (the SAME mechanism used successfully
all session) while the write-watch was active - zero hits for that too. This makes sense
in hindsight and isn't a bug: `memory.write_bytes_as_array` is a direct out-of-band poke,
not a real CPU-driven store instruction, so hardware watchpoints (which instrument the
actual CPU bus) correctly don't see it - a poke was never going to trigger a callback
built to catch real `STR`/`LDR` instructions. Redesigned the test properly: wrote
`UNLOCK_MASK_EVERYTHING` via the poke (fine, not what's being tested), then forced a REAL
screen reload (back out of character select, back in) - confirmed via screenshot that
more characters DID appear (Daisy/R.O.B./Wario/Waluigi/Bowser visible), proving the game
really did consult the new value to decide what to render... and the read-watch STILL
showed zero hits. This is a genuine, load-bearing, unresolved puzzle - not yet explained.
Leading candidate theory: ARM9 Data TCM (Tightly Coupled Memory) can provide a fast-path
for certain address ranges that bypasses the normal system bus the callback system
instruments (the same general category of quirk already found once this session for
Instruction TCM shadowing the ROM header) - untested, just the most plausible mechanism
given everything else about the watchpoint system checked out.

**Then a real incident**: tried a wildcard read-watch (`WATCHREAD ANY`, no address filter)
to check whether read-callbacks work AT ALL for this core/scope (ruling out a systemic
problem before chasing the TCM theory further). This is almost certainly what BizHawk's
own docs mean by "CPU-intensive" for the equivalent `on_bus_exec_any` - a wildcard read
callback fires on literally every memory read across the whole system, and the Lua
closure overhead per-call apparently cannot keep up in real time, resulting in a severe
slowdown that looked exactly like a hang (probe_log.txt stopped advancing entirely,
including for completely unrelated later macros that should have been trivial). Asked the
user to check on / restart BizHawk rather than continuing to poke a possibly-hung
process. **Lesson for next time: never use a wildcard (`ANY`) WATCHREAD/WATCHWRITE except
for the briefest possible deliberate test, and expect it might not be safely recoverable
without a restart - prefer a specific address whenever at all possible.**

Also fixed a real (unrelated, coincidentally harmless in this specific case) bug found
while investigating: `local addr = is_wildcard and nil or parse_hex(cmd[2])` is Lua's
classic `and/or`-as-ternary trap - when the "true" branch value is `nil` (or `false`),
the expression unconditionally evaluates the "or" branch instead, regardless of the
condition. Here `parse_hex("ANY")` happened to ALSO return `nil` (no valid hex digits),
so the bug was invisible in this one case - but it was still wrong, and would have broken
any future use of a differently-named wildcard keyword. Replaced with an explicit
`if/then` assignment.

### End-of-night consolidation: toolchain mystery, TCM-bypass theory strengthened, clear morning plan
User confirmed BizHawk hard-crashed (matches the wildcard-watch theory above), reopened
it and reconnected the script, and reported devkitARM/CMake/NCPatcher all set up, with
`editwl-bin` the one holdout (couldn't find a download). Researched `editwl-bin`
specifically: confirmed via GitHub's API that `XorTroll/editwl` has **zero releases and
zero tags** - there is no pre-built download, and its own README says building it needs
Qt on top of CMake, a real added dependency nobody had accounted for. Found a better
path instead: NCPatcher's own README recommends `nds-build`/`nds-extract` from
**Fireflower** (`MammaMiaTeam/Fireflower`) for the exact same "unpack ROM for patching,
repack afterward" role editwl-bin would have filled - and Fireflower DOES have a real
release with pre-built Windows binaries (`fireflower.zip`, verified via GitHub's release
API, no Qt needed). Gave the user this download directly; they confirmed it's installed.
mkds-re's own asmhack-examples still name NCPatcher+editwl-bin specifically, but there's
no indication the pairing is load-bearing rather than just "what the repo owner
personally uses" - Fireflower filling editwl-bin's specific ROM-unpack/repack role should
work fine, revisit only if something concrete breaks because of the substitution.

**Toolchain files could not actually be located on disk**, despite `DEVKITARM`/
`DEVKITPRO` environment variables being set (to MSYS2-style `/opt/devkitpro/...` paths
that this session's Git-Bash tool doesn't share a mount point with, unlike devkitPro's
own bundled MSYS2 shell). Found a real MSYS2 install at `C:\msys64` (unclear if it's
devkitPro's own bundled one or a pre-existing general-purpose install the user already
had) but `C:\msys64\opt\devkitpro` doesn't exist, and broad searches of `C:\`, `D:\`,
`F:\`, `G:\` top-level dirs, `%LOCALAPPDATA%`, `%PROGRAMFILES%`, and the user profile all
came up empty for `arm-none-eabi-gcc.exe` or any `*devkit*` folder. **Not resolved
tonight** - genuinely can't tell from here whether the devkitPro installer silently
failed, is still mid-installation, or put things somewhere not yet thought to check.
Flagging clearly for the user rather than guessing further or claiming the toolchain is
ready when it hasn't actually been verified to exist - **first thing to check together
in the morning**, before attempting any real build.

**Continued the RAM investigation carefully** (targeted addresses only, learned from the
crash) after BizHawk came back up. Two results, both negative but genuinely informative:
- Re-armed `WATCHWRITE`/`WATCHREAD` on `UNLOCK_FLAGS_ADDRESS` fresh (the crash/restart
  wiped all previously-registered watches, confirmed - this is expected, Lua state
  doesn't survive a BizHawk process restart) - not directly re-tested again since the
  SAME null result was already solidly established pre-crash (see above); moved straight
  to a follow-up test instead.
- Watched `g_SaveDataHolder`'s own pointer address (`0x0217AA08`, EU) for reads
  specifically - a plain static global, none of the heap-offset complexity of the
  dereferenced flags word. **Also zero hits**, navigating cleanly through title -> Single
  Player -> mode select -> Select Class (confirmed via screenshot: exactly 3 class
  options shown, no Mirror Mode 4th option, consistent with a clean post-crash save
  where the flags word is genuinely 0 again - not a broken test, a real clean baseline).
- Before trusting this, deliberately ruled out the two most likely mundane explanations:
  (1) whether the watchpoint API itself works at all - confirmed yes, both registrations
  returned real GUIDs with no errors, and an EARLIER test this session directly proved
  the mechanism catches a real, known call site (the `blx #0x2112ef0` sanity check during
  the disassembly work). (2) whether `EnableJIT` is silently on (which the C# source
  shows makes `.MemoryCallbacks` throw immediately, failing registration) - since BOTH
  registrations succeeded without error, JIT is confirmed OFF; this explanation is ruled
  out definitively, not just assumed.
- With both mundane explanations eliminated, the TCM-bypass theory from earlier tonight
  is now considerably better supported: it's not just ONE address behaving oddly, it's
  EVERY address tried in this whole region (the flags word AND its owning pointer)
  showing zero bus-visible activity despite definitively-proven real effects on game
  behavior. This increasingly looks like a genuine hardware/emulator-level limitation
  (data reads to this region resolving via a fast path the "ARM9 System Bus" callback
  scope cannot observe) rather than anything wrong with the watch target or methodology.

Left BizHawk in a clean, stable state (title/menu screen, all watchpoints explicitly
cleared) rather than mid-experiment, given the user is asleep and unavailable to help
recover from anything further going wrong overnight.

**Plan for the morning**: (1) figure out together where the toolchain actually lives, or
reinstall/rebuild it properly - this blocks ALL further forward progress on the ASM
patch specifically. (2) Given the watchpoint approach has now been thoroughly, carefully
exhausted for this specific address with a well-supported "hardware bypass" explanation,
static disassembly (the `reference/asm_tools/mkds_disasm.py` toolkit from earlier
tonight) remains the more promising path for actually locating the character-select
population logic - specifically the still-untried "search for inline bit-test patterns
against the known offset" idea already flagged in that file's own docstring, since two
independent lines of evidence now suggest there may genuinely be no function call to find
at all.

---

## Session 2026-08-05: toolchain located, `g_SaveDataHolder+0x70` confirmed live, function-symbol reliability concern found

User provided the actual install paths: `F:\devkitPro\`, `F:\fireflower\`, `F:\cmake-4.4.2\`
(and rebooted BizHawk fresh). Verified each on disk rather than trusting the paths blind:

- **devkitARM: real and complete.** `F:\devkitPro\devkitARM\bin\` has `arm-none-eabi-gcc.exe`
  (16.1.0), `-ld.exe`, `-objcopy.exe`, `-as.exe`, `-nm.exe`, `-objdump.exe`, etc. - a genuine
  ARM cross-compiler toolchain, ready to use directly.
- **Fireflower: real and complete.** `F:\fireflower\` has `nds-build.exe`/`nds-extract.exe`
  (+ `blz.dll`/`nfsfsh.dll`) - the pack/unpack tool the user installed last night as the
  editwl-bin substitute. Confirmed present and usable.
- **NCPatcher itself: NOT present anywhere** (whole-`F:` recursive search found only the
  reference `ncpatcher.json` example already in `mkds-re`, no actual binary or source clone).
  **`cmake-4.4.2` is unbuilt SOURCE**, not a built `cmake.exe` (no `cmake.exe` found anywhere
  on `F:`) - "CMake is done extracting" last night meant the source tarball, not a finished
  build. Building NCPatcher would mean bootstrapping cmake from source first, then cloning
  and building NCPatcher itself against it - a lot of extra fragile infrastructure for a tool
  that's fundamentally just an orchestration layer over devkitARM + a packer, both of which
  are already directly available. **Decision: skip NCPatcher entirely, drive
  `arm-none-eabi-gcc`/`ld`/`objcopy` and Fireflower directly via custom Python tooling** when
  actually building the hook - more predictable than fighting an unfamiliar tool's expected
  project layout, and avoids the cmake-bootstrap detour completely.

### `g_SaveDataHolder` dereferences to `0x023CE270` - CONFIRMED LIVE, not just arithmetic coincidence

Last session's "hypothesis" (deref lands on `0x023CE270`, `+0x70` = `UNLOCK_FLAGS_ADDRESS`)
was only ever inferred from a write-test side effect, never actually read directly - the
watchpoint on `g_SaveDataHolder`'s own address had zero hits all night, so its VALUE was
never observed. With BizHawk back up (mid-race, user actively playing), sent a one-shot
`READAT 0217AA08 4` via the existing macro protocol: **bytes `70 E2 3C 02` little-endian =
`0x023CE270` exactly.** `0x023CE270 + 0x70 = 0x023CE2E0` = `UNLOCK_FLAGS_ADDRESS`, confirmed
with certainty. Cheap, safe, read-only - didn't touch the user's active race.

### New search technique: literal-pool cross-referencing (`find_literal_refs.py`)

Built a second static-analysis tool (`reference/asm_tools/find_literal_refs.py`), since the
existing `resilient_scan_for_calls` (finds `BL`/`BLX` to named functions) is blind to inline
bit-tests with no function call. New approach: find every raw occurrence of
`g_SaveDataHolder`'s OWN address (`0x0217AA08`, a compile-time constant - unlike the
heap-derived `0x023CE2E0` which can't appear literally in code) in the binary, then scan
backward for the `LDR Rd,[PC,#imm]` instruction (ARM or THUMB literal-pool load) that
actually references each occurrence, with manual-review disassembly context printed for each
hit. Found **~24 real, cleanly-disassembling reference sites** across main ARM9 + overlays 0
and 1 (none in overlay 2/3). Nearly all of them are the SAME pattern: deref
`g_SaveDataHolder`, read the byte at `+0x28` (`SaveDataHolder.is_busy` per mkds-eu-types.h),
branch on it - a "wait for save data to be ready" guard used all over the place, not
unlock-flag related. A cluster in overlay 1 (~0x02198xxx-0x0219Dxxx) does bit-level
set/clear on a DIFFERENT byte, `sv_header + 0x31` (double indirection: deref
`g_SaveDataHolder`, then deref its `sv_header` field at struct offset `+0x0`), across several
individual bit masks (1, 8, 0x10, and a 2-bit sub-field using 2/4/6) - looked promising at
first, but every one of these sites calls `WriteSaveDataSectionHeaderToSaveData_from_thumb`
(`0x02056D40`, confirmed via `mkds-eu-symbols.x`) right after, which means `+0x31` is a
"section needs saving" dirty-flag byte, not the unlock flags - a red herring, documented here
so it isn't re-investigated later. **None of the ~24 sites touch the `+0x70` offset** that
`UNLOCK_FLAGS_ADDRESS` actually lives at.

### Real concern found: named FUNCTION symbols from mkds-re don't hold up under close inspection

Went to check `GetCurrentCharacterUnlockSecretFlags` (`0x02090B24`) and
`CheckSavedSecretFlag_from_thumb` (`0x02056DEC`) directly, since their names are exactly what
this investigation needs. Neither checked out:

- `GetCurrentCharacterUnlockSecretFlags @ 0x02090B24`: disassembles coherently in ARM mode,
  but widening the window backward shows `0x02090B24` is NOT a function start - it's 0x18
  bytes INTO a function that actually starts at `0x02090B0C` (real `stmdb sp!,{lr}`
  prologue). The surrounding code touches a completely different struct (offset patterns like
  `+0x1000+0xf40/+0xf52/+0xf55/+0x8e8`) with no visible connection to save data at all.
- `CheckSavedSecretFlag_from_thumb @ 0x02056DEC`: raw bytes at this exact address
  (`1E FF 2F E1`) are the literal ARM encoding for `BX LR` - a one-instruction stub that
  returns immediately, doing nothing. Re-ran the ORIGINAL `resilient_scan_for_calls` fresh
  to check reproducibility: **found 10 real `BL` call sites** (all THUMB, all in overlay 1,
  e.g. `0x02194CDE`, `0x021A12FA`, ...) genuinely targeting this exact address (cross-checked
  capstone's target computation isn't a fluke - tried to hand-verify the THUMB BL bit-encoding
  manually and got a different answer, but concluded my own by-hand decode is more likely
  buggy than capstone's mature implementation, since 10 independent call sites landing on the
  same meaningful address isn't consistent with random misalignment noise). Since a plain
  `BL` (not `BLX`) keeps the CPU in THUMB state at the target, and THUMB decode at
  `0x02056DEC` is immediate garbage (a nonsense NEON opcode - this binary doesn't use NEON),
  there's a genuine unresolved contradiction: 10 real call sites, but the callee looks like
  either a no-op (ARM reading) or garbage (THUMB reading).

**Conclusion: don't trust mkds-re's function-address symbols blindly going forward.** Every
DATA/struct-layout address used this whole project (`UNLOCK_FLAGS_ADDRESS`,
`RACECONFIGMANAGER_ADDRESS`, `GLOBAL_TROPHY_RESULT_POINTER_ADDRESS`,
`COURSE_ID_ORDERED_TABLE_ADDRESS`, `g_SaveDataHolder` itself) has been 100% reliable under
live testing. But no FUNCTION address has actually been independently confirmed live this
entire project - only inferred from static cross-referencing, which just produced two
contradictions in a row. Possible explanations not yet distinguished: a ROM-revision mismatch
specific to function layout (data layout could easily still match even if some code shifted),
a bug in how mkds-re itself extracted function boundaries, or something about the
`_from_thumb` naming convention that isn't understood correctly. Not resolved - flagging
prominently rather than continuing to build on an assumption that just failed twice.

### Live watchpoints re-armed (passive, safe during active gameplay)

User was mid-race when this was found - did NOT script any macro button inputs (would
interfere with a real human play session), but registering a watchpoint is pure event-hook
observation with zero effect on the running game, so armed two fresh ones to catch real
evidence the next time ANY menu screen loads naturally during normal play:
`WATCHREAD 0217AA08 saveholder_ptr_read2` and `WATCHREAD 023CE2E0 flags_word_read2`. This
sidesteps the whole function-symbol-reliability question - whatever PC/LR these catch IS the
real checking code, regardless of what name (if any) mkds-re assigns to that address.

User confirmed no longer racing ("not in a race, do what you need") - proceeded to actually
navigate the menus via the macro PRESS protocol (title -> Single Player -> Grand Prix ->
Select Class -> Character Select), screenshotting between steps. **Both data watches stayed
at 0 hits through the ENTIRE navigation, including landing on Character Select itself**
(which visibly shows only the 8 starters - confirms the screen's content genuinely depends on
this data, yet the read still isn't bus-visible). This is now about as solid as "zero hits"
evidence gets - the TCM-bypass (or similar fast-path) theory for DATA reads to this address
range is essentially confirmed at this point.

### `WATCHEXEC` added to probe.lua - and it WORKS (unlike the data watches)

Added a new macro command, `WATCHEXEC <addr> <label>` (`event.on_bus_exec`, modeled directly
on the existing WATCHREAD/WATCHWRITE code path) to test whether a specific CODE address is
ever reached - deliberately did NOT allow "ANY" wildcard for this one (a wildcard exec watch
fires on literally every instruction fetched, which would be even worse than the wildcard
READ that hard-crashed BizHawk once already - see earlier in this file). Needed a manual
script reload (auto-reload wasn't active this session) - user handled it.

Tested on the two addresses from the earlier symbol-reliability concern:
`CheckSavedSecretFlag_from_thumb` (`0x02056DEC`) and the TRUE start of the function mkds-re
calls `GetCurrentCharacterUnlockSecretFlags` (`0x02090B0C`, not `...B24` - see above). **Both
registered successfully and both show 0 hits after a full fresh Character Select load** -
confirming the exec-watch MECHANISM itself works fine (registration succeeded, no crash, no
error), while definitively proving neither address is actually reached. This resolves the
earlier contradiction: those two mkds-re symbols are simply not on the path Character Select
actually takes, for whatever reason (stale/wrong symbol data, ROM revision mismatch, or a
misunderstanding of the naming convention - still not determined which).

Went further: registered `WATCHEXEC` on ALL 21 of the real, statically-confirmed
`g_SaveDataHolder` reference sites found in overlay 1 (the confirmed select-screen overlay -
see the literal-pool cross-referencing section above) simultaneously - all 21 registered
without issue (individual specific-address watches are cheap; this is not the wildcard
danger case). Backed out of Character Select and back in to force a fresh load with all 21
armed. **All 21 show 0 hits.** Combined with the 2 above, that's 23 real, independently-
verified candidate addresses now DEFINITIVELY ruled out as part of Character Select's actual
code path. The `is_busy`/`sv_header+0x31` code cluster found via literal-pool
cross-referencing is real and does execute somewhere in the game, just not for this specific
screen.

### Found a real data table (not code) encoding 8 of the known unlock bits - overlay 3

Reframed the search: instead of hunting for the CHECK code, hunt for a DATA TABLE the
(unknown) check code might read from - if baseline/starter slots just carry a "no
requirement" sentinel in such a table, the table could be patched directly without ever
finding the code. Searched all regions for the raw bytes of every individually-known unlock
mask (`Daisy=0x00200000`, `Waluigi=0x00400000`, `R.O.B.=0x00800000`,
`Dry Bones group=0x001E0000`, plus the cup/mode bits) - most matches were noise (small masks
like `Leaf Cup=0x100`/`Mirror=0x10000` coincidentally appear hundreds of times as unrelated
immediates), but one cluster stood out: in **overlay 3** (`0x021B7BA0-0x021D7C40`, not
previously characterized - no string-search work done on this one yet, unlike overlays 0/1),
at `0x021D3695-0x021D36B4` sits a clean run of exactly 8 consecutive 4-byte values:
`0x00010000, 0x00020000, 0x00040000, 0x00080000, 0x00100000, 0x00200000, 0x00400000,
0x00800000` - i.e. `1<<16` through `1<<23`, walking bit-by-bit through EXACTLY the range this
project's empirical bit map covers (Mirror Mode=16, the 4 "Dry Bones group" bits=17-20,
Daisy=21, Waluigi=22, R.O.B.=23). Real code (THUMB instructions) immediately precedes it;
non-table-looking data immediately follows (`0x001B0000` then unstructured bytes) - so the
table's extent is almost certainly exactly these 8 entries, nothing before or after.

This is a genuinely new, different kind of lead - a per-BIT lookup table (probably index 0-7
-> `1<<(16+index)`), likely used by whatever code sets/tests these bits by small integer
index (matching the "pass 12 and 16 as arguments" calling convention seen earlier this
project). Notably it does NOT cover the cup bits (Leaf=8, Lightning=12) - starts right at 16.
Whether this is "the" table the character-select population loop reads (with baseline
characters using an out-of-range/sentinel index) or a more generic bit-shift utility table is
NOT yet determined - overlay 3's overall purpose hasn't been characterized yet (no string
search done on it, unlike overlays 0/1). This is the most promising unexplored thread if this
investigation continues.

**Status checkpoint**: after extensive effort across two sessions (data watchpoints on 2
addresses across many navigation states, static disassembly via 2 different techniques,
exec watchpoints on 23 real candidate addresses, and now a raw data-table search), the exact
character-select population/check code still has not been pinpointed, though the
watchpoint-based elimination has been thorough enough to be confident about what it ISN'T.
Checked in with the user: told to keep chasing the overlay-3 table lead specifically.

### Overlay-3 table refuted; the same search in the CORRECT overlay comes up empty too

Searched for what code references the overlay-3 table's address (`0x021D3695`), via both
addressing forms compilers actually use (`LDR Rd,[PC,#imm]` literal-pool loads, already had
this; added `ADR`/`ADD Rd,PC,#imm` PC-relative address computation, a real gap in the
existing tooling). **Zero references of either kind, anywhere in the ROM** - and a plain raw
byte search for `0x021D3695` as a stored pointer value (the same technique that reliably
finds `g_SaveDataHolder` refs) ALSO found nothing. No code or data anywhere points at this
table.

Pulled overlay 3's strings to understand what it actually is, since that had never been
checked (only overlays 0/1 had been string-searched before now): it's unambiguously the
**Nintendo Wi-Fi Connection (WFC) setup overlay** - `DWCi_MOV_WH_SYSSTATE_*`, `ESSID-AOSS`,
`NWCUSBAP`, and dozens of `char/jb4Hl{Wep,Ip,Gateway,Dns0,Dns1,Mask,Ssid,Usb}.nsc.l` asset
paths (the WEP-key/IP-address/DNS keyboard-entry screens of the network setup wizard). Not
character-select-related at all - the clean 8-entry bit sequence is almost certainly
coincidental (or a real table for something WiFi-related, e.g. channel/security flags), not
the character/cup unlock table. Lead refuted.

Re-ran the "find sequential power-of-2 runs" search specifically constrained to main ARM9 +
overlay 0 + overlay 1 (skipping overlay 3 and the tiny overlay 2), to check the RIGHT places
this time. Also finally string-searched **overlay 0** (shares overlay 1's RAM address,
previously untested - see the "likely a different scene entirely" note from last session):
it's ALSO WFC-related (GameSpy SDK strings - `gs.nintendowifi.net`, `GPI_NOT_CONNECTED`,
Thawte/GlobalSign SSL root CA names, `"CD Key or challenge too long"`) - confirms overlays 0
and 3 are BOTH online-play infrastructure, mutually exclusive alternates at the same RAM slot
as overlay 1 depending on whether you're setting up WFC or browsing local menus. The pow2-run
search DID find one more candidate, in overlay 0 at `0x02194048` (bits 14-18, only a partial/
imperfect match to the known unlock bits) - but given overlay 0's now-confirmed WFC purpose,
this is almost certainly the same kind of false positive as the overlay-3 table and wasn't
investigated further.

**Overlay 1 itself - the one confirmed (via strings, last session) to actually be the
select-screen overlay - has ZERO sequential power-of-2 runs of length >=4 anywhere in it.**
This is a clean, meaningful negative result: if a simple contiguous index->bitmask lookup
table exists for character/cup unlocking, it is not sitting in the one overlay definitely
responsible for that UI. Combined with the earlier 23-address exec-watch elimination (also
all within overlay 1), this now argues fairly strongly AWAY from "there's a tidy shared table
plus a shared check function" and TOWARD "the real logic is inline, per-character, scattered
through a larger population routine" - which is much less tractable to find via any of the
techniques tried so far (no clean single call site or table to search for).

Reported this back to the user rather than inventing further speculative search techniques
unprompted - two consecutive concrete leads (the table, then the overlay-0 partial match)
both resolved to false positives within the same session, which is a meaningful signal about
diminishing returns on this specific style of search.
