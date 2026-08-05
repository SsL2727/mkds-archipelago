# Mario Kart DS - Archipelago

A custom [Archipelago](https://archipelago.gg) world (multiworld randomizer integration) for
**Mario Kart DS**, targeting the EU ROM (gamecode `AMCP`) via BizHawk's melonDS core.

This repo does **not** include the ROM. Supply your own legally-obtained EU Mario Kart DS
ROM to play.

## Getting the world

Download the packaged `.apworld` and a sample player YAML from the
**[Releases page](../../releases/latest)** rather than building from source - drop the
`.apworld` into your Archipelago install's `custom_worlds/` folder. Building from
`worlds/mkds/` yourself works too (see Layout below) if you want to modify it first.

## Layout

- [`worlds/mkds/`](worlds/mkds/) - the actual Archipelago world: items, locations, rules,
  region/goal logic, RAM addresses, and the BizHawk client integration. This is what gets
  packaged into an `.apworld` and dropped into an Archipelago install's `custom_worlds/`.
- [`worlds/mkds/docs/setup_en.md`](worlds/mkds/docs/setup_en.md) - player-facing setup guide
  and current implementation status.
- [`Instructions.txt`](Instructions.txt) - the original design spec this world was built
  from (options, item classification, goal types).
- [`mkds_test.yaml`](mkds_test.yaml) - a sample player YAML for generating a test seed.
- [`NOTES.md`](NOTES.md) - condensed, actively-maintained technical reference: architecture
  context, design decisions, and methodology lessons. Start here if you're picking this
  project back up.
- [`NOTES_ARCHIVE.md`](NOTES_ARCHIVE.md) - the full chronological session-by-session log
  `NOTES.md` was condensed from, including abandoned mechanisms and superseded findings.
  Reference only if you need the complete investigation trail behind something in
  `NOTES.md`.
- [`reference/asm_tools/`](reference/asm_tools/) - standalone Python tooling for statically
  analyzing the ROM (BLZ/LZ-Overlay decompression, NDS overlay-table parsing, ARM/THUMB
  disassembly via `capstone`, literal-pool cross-referencing). No BizHawk dependency - reads
  the ROM directly.
- [`reference/ram_probe/probe.lua`](reference/ram_probe/probe.lua) - a BizHawk Lua script
  for live RAM investigation (reads/writes/scans/hardware watchpoints), driven by a simple
  file-based trigger protocol so it can be automated externally rather than clicked through
  by hand.
- [`mkds-poptracker/`](mkds-poptracker/) - a
  [PopTracker](https://github.com/black-sliver/PopTracker) item tracker pack
  (schema-verified against PopTracker's docs, not yet live-tested - see its own README).
  Regenerable from the world's actual item/location data via
  `mkds-poptracker/generate_pack.py`, so it can't drift out of sync by hand-editing.

## Status

Core multiworld logic (items, locations, goal, BizHawk check-sending for Grand Prix races,
cup wins, and Mission Mode clears) is implemented and live-verified against real gameplay.

**Enforcement model**: Mario Kart DS has no internal flag governing its baseline content
(8 starter characters, their default karts, 4 of the 8 cups), and an extensive ASM-patch
investigation to restrict it at the binary level found no patch point (see
`NOTES_ARCHIVE.md`). Rather than leave that unenforced, the world forces everything
unlocked and moves enforcement to the check-sending side instead: a check only sends if
the character and kart actually used were legitimately received as items first. See
`worlds/mkds/docs/setup_en.md`'s "How enforcement works" section for the player-facing
explanation.

**Starting state**: each seed gives exactly one free unlock per section - one starting
character and one starting kart (any of all 36 real karts, not tied to the character -
both checked by name only, no item needed), and (for whichever of Cups/Time Trial/
Missions are turned on) one starting cup, track, and mission (a separate, location-based
mechanism - everything else in that section needs its own item). See `NOTES.md`'s "One
free unlock per section" and "All 36 karts individually unlockable" sections for the
implementation details, including a real fill-deadlock bug found and fixed while
building the latter.

Not yet live-verified: all 36 karts individually unlocking specifically (the read
mechanism it's built on was live-verified for the previous single-item design, but the
kart-name resolution and free-kart-by-name check themselves are new), the character/kart
identity reads for cup-win/mission-clear checks, and Time Trial's "Staff Ghost Beaten"
detection end-of-run signal (the finish-time decode itself is confirmed live - see
`NOTES.md`). See `setup_en.md` for current status specifics.
