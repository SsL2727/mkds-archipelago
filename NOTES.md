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

**Full category accessibility + fungible Trophy items (2026-08-06, replaced per-item
sequential unlock)**: every cup, time-trial track, and mission is a real AP location
whenever its category is part of the goal at all - not just a pre-chosen subset sized to
the configured required count. Per user direction: "even if one time trial is the
designated goal amount, all time trials must be accessible and give a check." The player
picks freely what to complete; only a plain COUNT of category-fungible Trophy items
actually received (`items.CUP_TROPHY_NAME`/`TIME_TRIAL_TROPHY_NAME`/`MISSION_TROPHY_NAME`)
satisfies completion - the standard Archipelago "any N of M" pattern
(`state.has(TROPHY_NAME, player, N)`, see `rules.py`'s `set_rules`). This entirely
replaces the earlier "position 0 free, every other position gated on its own directly-
named item" scheme described below (`_sequence_access_rule`, since removed). Individual
race placements (3rd/2nd/1st) and cup Silver/Bronze tiers remain bonus-only, same as
before: real checks along the way, never part of completion_condition. Cup wins are now
cumulative too (Bronze/Silver/Gold, mirroring race placements exactly) rather than a
single Gold-or-nothing check - see `client.py`'s `_check_cup_result`. Characters/Karts
are unaffected (still Useful, never access-rule-gated - see below).

**Bootstrap + Key gating layered back on top (2026-08-06, same day, second pass)**: per
direct follow-up feedback ("the new apworld starts with everything unlocked. The player
should only start with either 1 cup, time trial, or mission"), the "unlock order" that
was just removed above came back in a different shape. The "any N of M" full-
accessibility goal design is NOT reversed - every cup/track/mission in an active category
is still a real location and the goal is still a plain Trophy count - only the STARTING
reachability changed. Each ACTIVE category independently gets exactly ONE randomly-chosen
bootstrap location reachable with zero items (`rules.choose_category_bootstrap`, mirroring
`choose_character_unlock_order`/`choose_kart_unlock_order`'s own "random position, no item
needed" pattern) - every OTHER location in that category needs that category's own Key
item (`items.CUP_KEY_NAME`/`TIME_TRIAL_KEY_NAME`/`MISSION_KEY_NAME`), which opens the
ENTIRE rest of the category at once (not sequentially, unlike the original pre-"full
accessibility" design). If multiple categories are active, each gets its own independent
bootstrap + Key - three simultaneously-free starting locations if Cups + Time Trial +
Missions are all active, not one globally.

**A real capacity constraint forced an exception, found via a live `Generate.py` sweep
before shipping (not theoretical)**: Time Trial and Missions are THIN categories (exactly
1 location per track/mission, no tier multiplier the way Cups have via Win/Silver/Bronze x
4 tracks x 3 placements each). `__init__.create_items()` sizes each category's Trophy pool
to its own win TARGET now (not the full category list, unlike the first pass above) -
freeing room for the Key - but when target equals the full category size (an "_all" goal,
or a "_count" goal maxed to the category's full length), every one of that thin category's
locations is already claimed by a mandatory Trophy, leaving zero room for a Key at all.
Cups never hit this (120 locations across 8 cups vs. at most 9 mandatory items, always
abundant) - see the third pass below for how Time Trial/Missions resolve it now (this
capacity check was later generalized, not just a boolean anymore).

**Individual per-track/mission unlocking, capacity-solved per seed (2026-08-06, same day,
third pass)**: per a further direct follow-up ("don't unlock everything at once through
one item. Each time trial and mission should be unlocked individually"), the shared Key
from the second pass became a FALLBACK rather than the default for Time Trial/Missions
specifically (at this point Cups still used their own single shared Key - see the fourth
pass below for why that changed too). `rules.decide_unlock_modes` brute-forces, per seed,
whichever combination of three modes - `"individual"` (one directly-named Progression
item per non-bootstrap track/mission, `items.TRACK_UNLOCK_NAMES`/`MISSION_UNLOCK_NAMES` -
just the track/mission's own name, mirroring the OLDEST pre-2026-08-06 design and
Characters/Karts' own "one free by name, the rest individually named" shape),
`"shared_key"` (the second pass's design), `"open"` (the first pass's design, no gating
item at all) - actually fits this seed's real mandatory-item count within its real
location count, preferring individual over shared_key over open. Only 3x3=9 combinations
exist (Time Trial x Missions), so it just checks all of them rather than a hand-tuned
heuristic - guaranteed to find the actual best fit, and always finds SOME feasible
combination (`("open", "open")`'s demand is only each category's own win target, which can
never exceed that category's own location count by construction).
`world.time_trial_unlock_mode`/`mission_unlock_mode` (strings, replacing the second pass's
`time_trial_key_active`/`mission_key_active` booleans) hold the result.

**Cups join individual unlocking too, unconditionally (2026-08-06, same day, fourth
pass)**: per a further direct follow-up ("Cups should also be unlocked individually along
with drivers and karts. Everything should be unlocked individually"), Cups moved off the
shared "Cup Key" entirely - `items.CUP_KEY_NAME` no longer exists. Cups now use the exact
same one-directly-named-item-per-non-bootstrap-entry pattern as Characters/Karts and as
Time Trial/Missions' own default (`items.CUP_UNLOCK_NAMES` - just the cup's own name), but
UNCONDITIONALLY, with no fallback machinery of Cups' own: even the worst case (`cups_all`,
all 8 required) needs only 7 unlock items + 8 Trophy = 15 mandatory items against 120 real
cup-category locations (8 cups x 12 locations each - 3 own tiers + 4 tracks x 3
placements) - always comfortably capacity-safe, proven, not assumed. Cups' own mandatory
demand still feeds into `rules.decide_unlock_modes`' capacity accounting for Time
Trial/Missions (they all draw from the same global `location_count` pool), just as a fixed
input rather than something the solver chooses among modes for. Verified live: a 4-player
`Generate.py` run combining `cups_all` (the worst case for cups' own demand) with
Characters/Karts on, a modest-target combination goal expected to land on individual mode
across all three categories, a fully-maxed "everything at once" combination, and Time
Trial alone at max (the thinnest single-category case) all generated together without
error - `test.TestCupIndividualUnlock` is the direct reachability regression (mirroring
`test.TestIndividualUnlockWhenCapacityAllows`'s pattern for Time Trial/Missions) proving a
sample non-bootstrap cup (and its own tracks) is unreachable with zero items, stays
unreachable after receiving some OTHER cup's own item, and becomes reachable only once its
OWN specific item is received; `test.TestTimeTrialSharedKeyFallback`/
`MissionSharedKeyFallback` and the renamed `TestKartsWithThinCategoryNoLongerDeadlocks`
still cover the shared_key and open fallbacks for Time Trial/Missions specifically (Cups
never need either). **Superseded by the fifth pass immediately below** - once the Trophy
item was removed entirely, the shared_key/open fallback machinery this paragraph
describes turned out to be unnecessary too (see below) and was deleted; kept here only for
the historical record of how the capacity problem was first solved.

**All fungible "Trophy" items removed entirely - completion is now checked against real
location completion, not a received item count (2026-08-06, same day, fifth pass)**: per
direct user direction, correcting a real design flaw: "I do not want any item that counts
towards the goal. The only thing that counts towards the goal is complete the cup, time
trial, or the mission." The flaw: `items.CUP_TROPHY_NAME`/`TIME_TRIAL_TROPHY_NAME`/
`MISSION_TROPHY_NAME` were ordinary shuffled Progression items, so the fill algorithm
could place any given copy at ANY reachable location - not necessarily the specific
cup/track/mission it nominally represented - meaning a player could satisfy the goal by
receiving N Trophy copies from unrelated checks (or another player's world) without
actually completing that many cups/tracks/missions themselves. All three Trophy items and
their build_item_table() entries are gone; `rules.py`'s `completion_condition` now checks
`state.can_reach_location(...)` directly against each active category's required
locations (their own "- Win"/"- Staff Ghost Beaten"/"- Clear" locations), and
`client.py`'s `_check_goal_complete` (the real-time trigger that actually calls
`ClientStatus.CLIENT_GOAL`) was rewritten to read `ctx.checked_locations` directly against
each category's required win count, reviving the pre-"any N of M" design's own mechanism
(see this file's git history) rather than counting received items.

Two consequences worth remembering: (1) since `required_cups_in_order`/etc. are always
the FULL category (never a subset sized to the configured count -
`choose_goal_required_cups`/`_time_trials`/`_missions` haven't changed), generation-time
`completion_condition` ends up requiring the ENTIRE category reachable regardless of the
configured `required_cup_count`/etc - AP's logic-state solver has no way to represent "the
player will choose to stop after N of their own choosing", so this is a deliberate,
documented superset of the real requirement; the actual "any N of M" enforcement is purely
a client.py/real-time concept now. (2) Without a Trophy item competing for room, every
category's individual-unlock demand dropped to a flat `(M - 1)`, which is ALWAYS less than
its own `M` real locations - so the elaborate `rules.decide_unlock_modes` capacity solver
(and `items.TIME_TRIAL_KEY_NAME`/`MISSION_KEY_NAME`, its shared-Key fallback) became
unnecessary and was deleted entirely; Cups, Time Trial, and Missions all now
unconditionally use individual unlocking, no fallback of any kind, exactly like
Characters/Karts always have. Verified live: a 3-player `Generate.py` run (a fully-maxed
"everything at once" combination, `mission_mode_complete` alone with Characters/Karts on,
and a small `cups_count=2` seed) generated together without error, and the spoiler log
confirms zero remaining "Trophy" references anywhere.

**Two more real client.py bugs found and fixed the same day, both from direct live
playtesting**:
- Cup check-sending simplified: a Bronze-or-Silver-only cup finish was reported sending
  ZERO checks (the cumulative Bronze/Silver/Gold design from earlier the same day never
  got root-caused) - per direct user direction ("just make first place get 3 checks"),
  `_check_cup_result` now only sends anything on an actual Gold (1st place overall)
  finish, sending all three cup locations ("- Bronze"/"- Silver"/"- Win") together at that
  point - Bronze/Silver-only finishes send nothing, sidestepping whatever the original bug
  was rather than chasing it.
- Mission win false-positive on start: `_check_mission_result`'s win signal
  (`RACESTATUS_OFFSET_MISSION_WIN_DELAY_COUNTER` being nonzero) fired immediately on
  entering some missions, not on completing them - almost certainly leftover heap content
  at a freshly-allocated RaceStatus's memory (mkds-re's data offsets have otherwise been
  100% reliable, see this file's own methodology section, so this reads as an
  uninitialized-memory issue, not a wrong offset). Fixed by requiring an explicit
  CONFIRMED-ZERO reading for the current race_status_ptr before a nonzero reading is ever
  trusted as a real win (`mkds_mission_zero_confirmed`, reset alongside
  `mkds_mission_win_seen` on every new race instance) - not yet re-confirmed live by the
  user as of this note.

**PopTracker's progress counters, broken by the same-day Trophy removal, fixed and
delivered** (self-identified, not user-reported): the pack's `progress_cups`/
`progress_time_trial`/`progress_missions` "X/Y" overlays used to count RECEIVED Trophy
items (`mkds-poptracker/scripts/autotracking.lua`'s old `trophy_counts` table) - with
Trophy items removed apworld-side, that would have shipped permanently stuck at "0/0".
Fixed by generating a new `scripts/progress_categories.lua` mapping every top-tier
location name/id (cup "- Win", track "- Staff Ghost Beaten", mission "- Clear") to its
progress category, and switching `autotracking.lua` to count CHECKED locations via
`Archipelago:AddLocationHandler`/`Archipelago.CheckedLocations` instead of received
items - mirroring exactly what `worlds/mkds/rules.py`'s `completion_condition` and
`client.py`'s `_check_goal_complete` now check. Verified: pack regenerated
(`generate_pack.py`), all JSON parses and every referenced image exists, all `.lua`
files pass a brace/paren/bracket balance check, and `mkds-poptracker.zip` rebuilt
(package_version stays `0.12.0` - this is the first delivery of that version, bundling
both the cup-accessibility fix and this progress-counter fix together, since 0.12.0 was
never shipped on its own). Not yet live-tested against a real PopTracker install, same
honesty flag as the rest of this pack.

**PopTracker Time Trial/Missions still showed no "unlocked" state after delivery -
user-reported the next day, root-caused as an over-correction, fixed 2026-08-07**: the
0.12.0 delivery above still didn't show missions/time trials as unlocked. The user pointed
at a specific earlier point in the session ("go look at the code from around 2 am this
morning") - `git log`/`git show` on the one commit touching `mkds-poptracker`
(`a5a6767`, "rework PopTracker pack") confirmed that version had a genuine 3-stage
locked/unlocked/completed progressive-item design for Cups/Tracks/Missions. The
session's own third redesign pass (this same file, above) had reverted Time Trial/
Missions to a 2-stage format per a literal reading of "revert to the previous functioning
code" - but that reverted PAST the working 3-stage version to an even older design that
never showed "unlocked" at all, over-correcting rather than just fixing the two real Cup
bugs that prompted it. Fixed by restoring a 3-stage design (locked/unlocked/completed) for
Time Trial/Missions, reusing the pack's real per-track/mission artwork (grey `img_mods`
tint for locked, full color for unlocked, the generic checked icon for completed) rather
than the 2 am version's generic placeholder art. This also fixed a real latent bug: Time
Trial/Mission unlock items were never looked up by `ITEM_NAME_TO_CODE` at all, so
receiving one was silently a no-op regardless of display format - see
`mkds-poptracker/scripts/progressive_item_codes.lua` (new) and `autotracking.lua`'s
`onItemReceived`/`activate_bootstrap_progressive`.

**`mkds-poptracker/generate_pack.py` was found missing from disk while investigating the
above** (never committed - `git log -- mkds-poptracker` shows only one historical commit,
predating most of this session's redesigns; everything since was uncommitted working-tree
state, and the file was apparently lost partway through an earlier edit this session,
root cause not identified). Reconstructed from scratch by reverse-engineering the
still-present, still-correct generated output on disk (`items/items.json`,
`locations/*.json`, `maps/maps.json`, `scripts/*.lua`) cross-referenced against
`worlds/mkds`'s own source tables - real MKDS artwork filenames (`CHAR_ICON`/`KART_ICON`/
`TRACK_ICON`/`MISSION_ICON`/`CUP_ICON`) were extracted directly from the last-known-good
`items.json` rather than re-guessed. Verified before layering the 3-stage fix on top: every
regenerated file except `items.json` itself (which was expected to change) came out
byte-identical (JSON/Lua) or pixel-identical (`cups_grid.png`/`gp_placements_grid.png`,
diffed via `PIL.ImageChops.difference`) against the pre-reconstruction output.
`mkds-poptracker.zip` rebuilt and delivered at `package_version` `0.13.0`. Lesson: this
project's git history discipline (commit real milestones, not just deliver zips) has a
real gap here - `mkds-poptracker/` has had exactly one commit across dozens of redesign
passes this session, which is why nothing could be recovered from git when a file went
missing.

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

**Missions are unconditionally reachable whenever Mission Mode is part of the goal at
all** (like every category, per the 2026-08-06 redesign above). Randomize Mission Mode
still only controls whether Mission Mode participates in the AP economy at all - slot
shuffling (which mission occupies which level position) was dropped separately and stays
dropped; only *access* changed, not vanilla slot placement.

**`create_regions` only instantiates goal-required locations**, not the full ~198-location
table - matches Instructions.txt's actual design (non-required content isn't a real AP
location at all, not just "doesn't need an item"). If this ever changes, remember
`create_items`'s pool sizing and `rules.py`'s rule-iteration both currently assume it.

**REAL BUG FIXED 2026-08-07: `_is_run_legitimate` was reading the WRONG driver slot's
character/kart for races where the player isn't grid position 0** - user-reported
(`is_run_legitimate=False` despite confirmed-received items, then reproduced across
every cup, not just one). Root cause: `client.py` hardcoded `rom_addresses.
PLAYER_DRIVER_ID=0` everywhere it needed to know "which `drivers[]`/`racer_entries[]`
index is the player" - that constant's own comment already flagged the risk ("only
confirmed live for 2 races, both of which happened to read back 0... if client.py ever
needs this in a context where it could plausibly differ, read
`RACECONFIG_OFFSET_PLAYER_DRIVER_ID` live instead"), and this is exactly that case. Fixed
by adding `_read_player_driver_id` (reads `RaceConfig.player_driver_id` live off the
already-available `race_config_addr`) and threading its result through every callsite
that used to trust the hardcoded constant: `_check_race_result`'s own `place_driver_ids`
lookup (so a wrong slot no longer risks misidentifying which PLACE the player finished
in, not just which character/kart), `_check_cup_result`, and `_check_time_trial_result`.
Verified: unit tests (58/58, both dev copy and repackaged `.apworld`) and a relocate-
and-reload check confirming `world_version` `0.13.0` loads correctly from the zip. NOT
yet re-confirmed live by the user as of this note - the reasoning is solid (the
constant's own doc comment predicted this exact failure mode, and the user's symptom
matches it precisely) but this project's practice is to flag until actually re-tested.

**Mission check-on-start bug: root-caused and fixed 2026-08-07, second attempt** (the
first attempt - a 3-consecutive-zero-polls guard - also did not hold, per user
retest). The user's follow-up debug log was the key: `mission win detected: level=255,
stage=255` (255 is not a valid level/stage - max is 7/9), and the user explicitly
confirmed these debug lines appeared **while not even in a mission**. Root cause:
`_check_mission_result` was being called unconditionally every tick regardless of game
mode (it hangs off the same `race_status_ptr` used for Grand Prix/Time Trial), so
`RACESTATUS_OFFSET_MISSION_WIN_DELAY_COUNTER` was being read and TRUSTED even during
non-Mission race types, where that offset means something else (or nothing). Real fix:
read `cur_mission_level`/`cur_mission_stage` FIRST and only evaluate the win-delay
counter (and its zero-confirmation bookkeeping) while they're in valid range - i.e. only
trust this signal while genuinely inside Mission Mode. Dedup state now resets on EVERY
tick spent outside Mission Mode (not just on a `race_status_ptr` change), so a
false-positive from outside Mission Mode can no longer leak into a later real attempt.
Verified: unit tests (58/58, dev copy and repackaged `.apworld`) and a relocate-and-
reload check. NOT yet re-confirmed live - flagging per this project's established
practice, especially since the FIRST attempted fix for this same bug also failed live
testing.

**Character/kart legitimacy bug: the REAL root cause, found 2026-08-07 (the
`PLAYER_DRIVER_ID` fix above was real but incomplete)** - after that fix shipped, the
user's next debug log showed `player_driver_id=0` (correctly read live) and confirmed
the character/kart shown WAS what they were actually driving and that both items WERE
actually unlocked/received - yet `is_run_legitimate` still returned `False`. Root cause:
`validate_rom` set `ctx.items_handling = 0b001`, which per Archipelago's own network
protocol docs (`docs/network protocol.md`) means **"receive items sent from OTHER
worlds" ONLY** - it does NOT include items placed within the player's OWN MKDS world
(that requires 0b010 as well). An ordinary Fill placement can put any Character/Kart
item in the player's own world just as easily as anyone else's, so `ctx.items_received`
was silently missing every self-found copy - `_is_run_legitimate`'s `received_counts`
lookup would then read 0 for a genuinely-received item and fail legitimacy. In a
single-player game specifically, EVERY item is "from your own world," so `0b001` alone
would receive nothing beyond the free bootstrap entries at all - this is almost
certainly why it "worked two patches ago" (probably a different test context) and then
failed broadly once actually played. Fixed: `items_handling = 0b111` (matches the
"receive everything" pattern already used elsewhere in this codebase, e.g.
`CommonClient.py`'s own `/received` command). This is the higher-confidence fix of the
two found today - it's a documented protocol bitmask, not inferred behavior - but still
flagged unconfirmed pending live retest, same practice as everything else in this file.

**Four more real bugs found and fixed 2026-08-07, same day, from continued live
playtesting against the two fixes above:**

1. **Cup misidentification - winning Lightning Cup (and separately Banana Cup) both
   identified as Mushroom Cup.** `TROPHYRESULT_OFFSET_CUP_IDX` (StructTrophyResult's own
   cup_idx field) had only ever been live-confirmed against Mushroom Cup itself (idx 0) -
   indistinguishable from "always reads 0", which is exactly what it turned out to be.
   This also silently broke the `(cup_idx, player_rank)` dedup key `_check_cup_result`
   uses (two different cups finishing at the same rank looked like the same
   already-processed pair, so a later cup could be silently SKIPPED, not just
   misidentified). Fixed by reading cup_idx from `RaceConfig` instead
   (`RACECONFIG_OFFSET_CUP_IDX`), via the same `race_config_addr` already relied on for
   character/kart legitimacy at that exact moment - the user's own report confirmed "the
   car and driver are correct" at ceremony time, direct live evidence that struct's data
   is still fresh then. `rom_addresses.py`'s `TROPHYRESULT_OFFSET_CUP_IDX` now carries a
   loud "DO NOT USE" comment; nothing in `client.py` reads it anymore.
2. **Missions could still send a check immediately on entry** when going straight from
   one mission into another without leaving Mission Mode, or retrying after a fail.
   `_check_mission_result`'s dedup only reset on a `race_status_ptr` change - if the game
   reuses the same allocation across back-to-back missions, a genuinely new mission
   (different level/stage) wouldn't reset anything. Now keyed on
   `(race_status_ptr, level, stage)` together. Separately, once `zero_confirmed` became
   True it stayed true FOREVER for that key - now consumed/invalidated on every nonzero
   poll, requiring a fresh 3-poll zero streak before trusting the next nonzero again, not
   just once ever. Explicitly NOT claimed to fully resolve retry-after-fail specifically -
   two previous attempts at this exact bug each missed something, and without a live
   probe there's no way to confirm a FAILED attempt doesn't also trip the same counter
   (which would need a way to distinguish win from lose that hasn't been found yet).
3. **Completing a mission set on a real track could send that track's Time Trial check
   too** - confirmed via completing "Level 6 Mission 6" (staged on GCN Yoshi Circuit)
   also sending "GCN Yoshi Circuit - Staff Ghost Beaten". `_check_time_trial_result` had
   no way to tell a Mission Mode race-end from a genuine Time Trial finish when both
   happen to share a real course_id. Fixed with the same in-Mission-Mode gate
   `_check_mission_result` already uses (cur_mission_level/stage in valid range -> bail).
   This also plausibly explains a separately-reported symptom (Mission 4-9 "didn't send a
   check on completion but PopTracker showed it complete") if that mission's own
   win-delay false-positive (bug 2 above) fired early while this un-gated path was ALSO
   incidentally satisfied around the same time - not confirmed, but no longer possible
   either way now that both paths are gated.
4. **Goal fired immediately after another player's own goal completion, without this
   player having played the cup they still needed.** `_check_goal_complete` used to
   trust `ctx.checked_locations` (server-synced, supposed to be scoped to only this
   player's own checked locations per Archipelago's protocol) directly on every poll, and
   had NO debug logging at all - impossible to diagnose further from a single report.
   Added debug logging, and switched to a defense-in-depth design: goal completion now
   counts against `ctx.mkds_goal_confirmed_locations`, a set seeded ONCE per connection
   (reseeded fresh on every `validate_rom`, i.e. every reconnect) from whatever
   `ctx.checked_locations` already contained at that point, then grown ONLY by this
   client's own confirmed sends (`_record_own_check`, called from every location the
   game's own detection logic sends) for the rest of that connection. A location that
   becomes "checked" server-side mid-session through anything OTHER than this client's
   own live detection can no longer count toward the goal until a fresh reconnect
   re-establishes the baseline. The underlying mechanism that let this happen was not
   itself identified (no prior debug log existed for this path) - this satisfies the
   user's literal request as a safety net regardless of the exact original cause.

Verified (all four): unit tests (58/58, dev copy and repackaged `.apworld`), a real
2-player `Generate.py` sweep, and a relocate-and-reload check confirming `world_version`
`0.15.0` loads correctly from the zip. None of these four have been re-confirmed live by
the user as of this note - flagging honestly, especially given bug 2's fix is explicitly
a partial mitigation, not a proven resolution.

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

### One free unlock per section (superseded 2026-08-06 by full category accessibility)

The sequential per-item unlock scheme described in this section (and
`kart_bootstrap_exempt_locations`/the bootstrap-deadlock exemption right above it) no
longer exists in `rules.py` - see "Full category accessibility + fungible Trophy items"
and "Bootstrap + Key gating layered back on top" above for what replaced it (twice).
Kept below for the historical bug-fix reasoning (the bootstrap deadlock, the kart
fill-deadlock analysis) since both are still instructive, even though the specific
mechanism they were fixing has since been replaced with something that can't hit either
failure mode at all - the CURRENT bootstrap+Key design (see above) gates on a single
category-wide Key rather than a chain of per-item sequential unlocks, so there's no
"two mandatory items competing for the same bootstrap slot" shape to deadlock on, only a
flat capacity check (`*_key_active`) already handled explicitly.

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
