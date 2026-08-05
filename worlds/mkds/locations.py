# locations.py
#
# Location table for the Mario Kart DS world.
#
# The 32-track roster and cup groupings are now filled in with real data (see
# TRACKS_BY_CUP below for sourcing/confidence notes) - only 4 of the 32 are directly
# in-game-screenshot-verified, the rest are web-sourced and internally consistent but
# not yet individually confirmed against this exact ROM. The Mission Mode SLOT COUNT (7
# levels x 9 missions = 63) is confirmed via mkds-re's decompiled struct layout (see
# rom_addresses.py); mission objective text is now filled in too (see
# MISSION_OBJECTIVES_BY_LEVEL below for sourcing/confidence notes - boss names are
# cross-verified against two sources, the 56 non-boss objectives are single-sourced, same
# confidence tier as the unconfirmed tracks). Cup names and the clear-vs-3-star check
# split ARE confirmed (both against Instructions.txt and, for the clear/3-star split,
# against mkds-re's StructMissionLevelStageInfo.beaten/.rank fields).
#
# Every location below is only a real (item-granting) AP location if it's part of the
# goal-required subset for the seed - see rules.py for how that subset gets chosen and
# how non-required content instead just follows vanilla unlock progression.

from typing import NamedTuple, Optional

base_id = 0xADF800  # verified against 49/~90 bundled worlds, see items.py's base_id note


class LocationData(NamedTuple):
    code: Optional[int]
    region: str


CUPS = [
    "Mushroom Cup", "Flower Cup", "Star Cup", "Special Cup",
    "Shell Cup", "Banana Cup", "Leaf Cup", "Lightning Cup",
]

# Full 32-track roster by cup. Mushroom Cup's 4 are directly confirmed via an in-game
# screenshot (2026-08-04, see NOTES.md) and match the web sources exactly. The other 28
# are sourced from spong.com/mariowiki-derived search results (2026-08-04), not yet
# individually screenshot-verified in-game, but consistent across sources. Retro tracks
# are prefixed with their origin system (SNES/N64/GBA/GCN) - required to disambiguate
# real name collisions between retro tracks and their nitro/cross-retro namesakes (e.g.
# a GBA "Luigi Circuit" AND a separate GCN "Luigi Circuit" both exist as retro tracks;
# "Mario Circuit" the nitro track is distinct from SNES "Mario Circuit 1").
TRACKS_BY_CUP = {
    "Mushroom Cup": ["Figure-8 Circuit", "Yoshi Falls", "Cheep Cheep Beach", "Luigi's Mansion"],
    "Flower Cup": ["Desert Hills", "Delfino Square", "Waluigi Pinball", "Shroom Ridge"],
    "Star Cup": ["DK Pass", "Tick-Tock Clock", "Mario Circuit", "Airship Fortress"],
    "Special Cup": ["Wario Stadium", "Peach Gardens", "Bowser's Castle", "Rainbow Road"],
    "Shell Cup": ["SNES Mario Circuit 1", "N64 Moo Moo Farm", "GBA Peach Circuit", "GCN Luigi Circuit"],
    "Banana Cup": ["SNES Donut Plains 1", "N64 Frappe Snowland", "GBA Bowser Castle 2", "GCN Baby Park"],
    "Leaf Cup": ["SNES Koopa Beach 2", "N64 Choco Mountain", "GBA Luigi Circuit", "GCN Mushroom Bridge"],
    "Lightning Cup": ["SNES Choco Island 2", "N64 Banshee Boardwalk", "GBA Sky Garden", "GCN Yoshi Circuit"],
}
TRACKS = [track for tracks in TRACKS_BY_CUP.values() for track in tracks]

# Level/mission-count confirmed via mkds-re's SaveDataSection_MissionRun struct
# (2026-08-04): 7 levels, 9 mission "stage entries" each = 63 total slots (8 numbered
# objectives + 1 boss battle per level). Objective text below is web-sourced
# (mariolegacy.com's mission list, 2026-08-04) - NOT individually screenshot/in-game
# verified the way Mushroom Cup's 4 tracks were. The 7 BOSS names specifically ARE
# cross-checked against a second independent source (mariowiki.com's "List of boss
# arenas in Mario Kart DS") and two corrections applied where the sources disagreed
# (Level 1 "Big Bully", not "Big Bull"; Level 5 "Big Bob-omb", not "Big Bomb-Omb" -
# mariowiki's spelling matches the character's standard name elsewhere in the Mario
# franchise). The 56 non-boss objective descriptions are single-sourced - treat with the
# same confidence caveat as the 28 unconfirmed tracks in TRACKS_BY_CUP above. Which
# mission is "boss" (9th of each level) IS independently confirmed by mkds-re/general
# knowledge (every level ends in a boss fight), just not each boss's exact in-level
# numbering versus the community source's.
MISSION_LEVEL_COUNT = 7
MISSIONS_PER_LEVEL = 9
MISSION_OBJECTIVES_BY_LEVEL = [
    [
        "Drive through 5 numbered gates in order",
        "Collect all 15 coins",
        "Destroy all 10 item boxes",
        "Get the Star and use it to hit 5 Cheep Cheeps",
        "Drive through 6 numbered gates in order",
        "Drive out of the mansion, backward",
        "Collect all 20 coins",
        "Perform 4 power-slide turbo boosts in 1 lap",
        "Boss - Big Bully",
    ],
    [
        "Crash into and destroy all 10 wooden crates",
        "Collect all 10 coins",
        "Drive through 5 numbered gates in order",
        "Destroy all 5 item boxes",
        "Collect all 20 coins",
        "Use Bob-ombs to destroy all 5 Pokeys",
        "Drive through 10 numbered gates in order",
        "Perform 6 power-slide turbo boosts in 3 laps",
        "Boss - Eyerok",
    ],
    [
        "Destroy all 5 item boxes",
        "Drive through 5 numbered gates in order, backward",
        "Collect 15 coins while avoiding the Chain Chomp",
        "Reach the finish before Yoshi",
        "Drive through numbered gates in order",
        "Hit Monty Moles with shells 5 times",
        "Perform 10 power-slide turbo boosts in 1 lap",
        "Collect all 20 coins",
        "Boss - Goomboss",
    ],
    [
        "Reach the finish before Donkey Kong",
        "Blast 20 crabs",
        "Reach the finish before the red car",
        "Drive through 7 numbered gates in order",
        "Collect 15 coins without being squished by a Thwomp",
        "Break 10 item boxes while avoiding the Fake Items",
        "Drive through 10 gates",
        "Perform 9 power-slide turbo boosts in 1 lap",
        "Boss - King Boo",
    ],
    [
        "Reach the finish before the stray Chain Chomp",
        "Drive backward and collect 15 coins without hitting a snowman",
        "Destroy all 5 item boxes",
        "Drive through 10 numbered gates in order",
        "Complete 1 lap in the opposite direction within the time limit",
        "Collect all 18 coins",
        "Drive through 8 numbered gates in order",
        "Reach the finish before Mario",
        "Boss - Big Bob-omb",
    ],
    [
        "Drive backward across the spinning bridge without falling",
        "Get Stars and run over 15 Rocky Wrenches",
        "Collect all 20 coins",
        "Destroy all 10 item boxes",
        "Drive through 8 numbered gates in order",
        "Perform 14 power-slide turbo boosts in 1 lap",
        "Collect all 40 coins",
        "Reach the finish before Peach",
        "Boss - Chief Chilly",
    ],
    [
        "Perform 6 power-slide turbo boosts in 1 lap",
        "Reach the finish before Bowser",
        "Complete 2 laps within the time limit",
        "Use shells to defeat all 30 Goombas within the time limit",
        "Collect all 20 coins",
        "Drive through 8 numbered gates in order",
        "Drive backward and collect all 12 coins without hitting a burner",
        "Break all 10 item boxes while avoiding the Fake Items",
        "Boss - Wiggler",
    ],
]
assert len(MISSION_OBJECTIVES_BY_LEVEL) == MISSION_LEVEL_COUNT
assert all(len(level) == MISSIONS_PER_LEVEL for level in MISSION_OBJECTIVES_BY_LEVEL)

MISSIONS = [
    f"Level {lvl + 1} Mission {m + 1} - {objective}"
    for lvl, level_objectives in enumerate(MISSION_OBJECTIVES_BY_LEVEL)
    for m, objective in enumerate(level_objectives)
]


def build_location_table() -> dict[str, LocationData]:
    table: dict[str, LocationData] = {}
    next_id = base_id

    for cup in CUPS:
        table[f"{cup} - Win"] = LocationData(next_id, "Grand Prix")
        next_id += 1

    for track in TRACKS:
        table[f"{track} - 1st Place"] = LocationData(next_id, "Grand Prix")
        next_id += 1

    for track in TRACKS:
        table[f"{track} - Staff Ghost Beaten"] = LocationData(next_id, "Time Trial")
        next_id += 1

    for mission in MISSIONS:
        table[f"{mission} - Clear"] = LocationData(next_id, "Mission Mode")
        next_id += 1
        table[f"{mission} - 3 Stars"] = LocationData(next_id, "Mission Mode")
        next_id += 1

    return table


location_table = build_location_table()
