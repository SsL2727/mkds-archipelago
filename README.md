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
  context, design decisions, methodology lessons, and the current state of the (unresolved)
  ASM-patch investigation. Start here if you're picking this project back up.
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

## Status

Core multiworld logic (items, locations, goal, BizHawk check-sending for Grand Prix races,
cup wins, and Mission Mode clears) is implemented and live-verified against real gameplay.

**Known limitation**: Mario Kart DS treats its 8 starter characters, their starting karts,
and 4 of the 8 cups as always available, with no internal save flag gating that access -
this world can restrict everything else (via RAM writes to the game's own unlock-flags
word) but currently cannot suppress that baseline content in-game. See
`worlds/mkds/docs/setup_en.md`'s "Known limitation" section and `NOTES.md`'s ASM-patch
investigation for the full detail if you want to pick that up - extensive work has gone
into locating the right patch point without success so far.

Also not yet working: starting-kart item application, Time Trial staff-ghost-beat
detection, and Mission Mode "3 Stars" rank detection - see `setup_en.md` for specifics.
