# generate_pack.py
#
# Regenerates items/items.json, locations/cups.json, locations/grandPrixTracks.json,
# maps/maps.json, images/maps/*.png, layouts/layouts.json, and every scripts/*.lua lookup
# table directly from the real Archipelago world's own item/location tables - these files
# should never be hand-edited (a real bug in an earlier version of this pack came from
# exactly that: a hand-maintained lookup table drifted from the real AP item names - see
# NOTES.md). scripts/init.lua, scripts/autotracking.lua, manifest.json, and README.md are
# hand-written and untouched by this script.
#
# RECONSTRUCTED 2026-08-07 after this file was accidentally lost from disk (an empty
# `git log`/`git show` history for mkds-poptracker meant nothing had been committed since
# a much earlier redesign - see NOTES.md). Rebuilt from scratch by reverse-engineering the
# still-present, still-correct generated output on disk (items.json, locations/*.json,
# maps/maps.json, scripts/*.lua) plus worlds/mkds's own source tables - the real MKDS
# artwork filenames below (CHAR_ICON/KART_ICON/TRACK_ICON/MISSION_ICON/CUP_ICON) were
# extracted directly from the last-known-good items.json rather than re-guessed, and every
# entry is asserted against worlds.mkds's own name lists at import time below so a rename
# on the AP side fails loudly here instead of silently shipping a broken image reference.
#
# Usage: py generate_pack.py [path-to-Archipelago-checkout]
# Defaults to ../reference/Archipelago (this project's local dev checkout) if omitted.

import json
import re
import sys
from pathlib import Path

from PIL import Image

PACK_DIR = Path(__file__).parent
ap_path = Path(sys.argv[1]) if len(sys.argv) > 1 else PACK_DIR.parent / "reference" / "Archipelago"
sys.path.insert(0, str(ap_path))

from worlds.mkds.items import CHARACTERS, KARTS  # noqa: E402
from worlds.mkds.locations import (  # noqa: E402
    CUPS, TRACKS, TRACKS_BY_CUP, MISSIONS, MISSION_OBJECTIVES_BY_LEVEL, location_table,
)

# --- Hand-curated real MKDS artwork filenames (images/items/<file>) -----------------
# No formula links an AP name to its wiki-sourced image filename (kart icons especially
# are inconsistently named - "Standard_MR_icon.png" vs "MKDS_icon_B_Dasher.png" - so these
# are a flat lookup, not generated). Asserted against worlds.mkds's own name lists below.

CHAR_ICON = {
    "Mario": "images/items/Mario_MKDS_record_icon.png",
    "Donkey Kong": "images/items/DK_MKDS_record_icon.png",
    "Toad": "images/items/Toad_MKDS_record_icon.png",
    "Bowser": "images/items/Bowser_MKDS_record_icon.png",
    "Peach": "images/items/Peach_MKDS_record_icon.png",
    "Wario": "images/items/Wario_MKDS_record_icon.png",
    "Yoshi": "images/items/Yoshi_MKDS_record_icon.png",
    "Luigi": "images/items/Luigi_MKDS_record_icon.png",
    "Dry Bones": "images/items/Dry_Bones_MKDS_record_icon.png",
    "Daisy": "images/items/Daisy_MKDS_record_icon.png",
    "Waluigi": "images/items/Waluigi_MKDS_record_icon.png",
    "R.O.B.": "images/items/ROB_MKDS_record_icon.png",
}

KART_ICON = {
    "Standard MR": "images/items/Standard_MR_icon.png",
    "Shooting Star": "images/items/Shooting_Star_MKDS_icon.png",
    "B Dasher": "images/items/MKDS_icon_B_Dasher.png",
    "Standard DK": "images/items/Standard_DK_icon.png",
    "Wildlife": "images/items/Wildlife_icon.png",
    "Rambi Rider": "images/items/MKDS_icon_Rambi_Rider.png",
    "Standard TD": "images/items/MKDS_icon_Standard_TD.png",
    "Mushmellow": "images/items/Mushmellow_icon.png",
    "4-Wheel Cradle": "images/items/MKDS_icon_4-Wheel_Cradle.png",
    "Standard BW": "images/items/Standard_BW_icon.png",
    "Hurricane": "images/items/Hurricane_icon.png",
    "Tyrant": "images/items/MKDS_icon_Tyrant.png",
    "Standard PC": "images/items/MKDS_icon_Standard_PC.png",
    "Light Tripper": "images/items/MKDS_icon_Light_Tripper.png",
    "Royale": "images/items/Royale_icon.png",
    "Standard WR": "images/items/MKDS_icon_Standard_WR.png",
    "Brute": "images/items/Brute_icon.png",
    "Dragonfly": "images/items/Dragonfly_icon.png",
    "Standard YS": "images/items/Standard_YS_icon.png",
    "Egg 1": "images/items/Egg_1_icon.png",
    "Cucumber": "images/items/MKDS_icon_Cucumber.png",
    "Standard LG": "images/items/MKDS_icon_Standard_LG.png",
    "Poltergust 4000": "images/items/Poltergust_4000_icon.png",
    "Streamliner": "images/items/Streamliner_icon.png",
    "Standard DB": "images/items/MKDS_icon_Standard_DB.png",
    "Dry Bomber": "images/items/Dry_Bomber_icon.png",
    "Banisher": "images/items/MKDS_icon_Banisher.png",
    "Standard DS": "images/items/MKDS_icon_Standard_DS.png",
    "Light Dancer": "images/items/MKDS_icon_Light_Tripper.png",
    "Power Flower": "images/items/Power_Flower_icon.png",
    "Standard WL": "images/items/MKDS_icon_Standard_WL.png",
    "Gold Mantis": "images/items/Gold_Mantis_icon.png",
    "Zipper": "images/items/Zipper_icon.png",
    "Standard RB": "images/items/MKDS_icon_Standard_RB.png",
    "ROB-BLS": "images/items/ROB-BLS_icon.png",
    "ROB-LGS": "images/items/ROB-LGS_icon.png",
}

TRACK_ICON = {
    "Figure-8 Circuit": "images/items/MKDS_Figure_8_Circuit_Course_Icon.png",
    "Yoshi Falls": "images/items/MKDS_Yoshi_Falls_Course_Icon.png",
    "Cheep Cheep Beach": "images/items/MKDS_Cheep_Cheep_Beach_Course_Icon.png",
    "Luigi's Mansion": "images/items/MKDS_Luigi's_Mansion_Course_Icon.png",
    "Desert Hills": "images/items/MKDS_Desert_Hills_Course_Icon.png",
    "Delfino Square": "images/items/MKDS_Delfino_Square_Course_Icon.png",
    "Waluigi Pinball": "images/items/MKDS_Waluigi_Pinball_Course_Icon.png",
    "Shroom Ridge": "images/items/MKDS_Shroom_Ridge_Course_Icon.png",
    "DK Pass": "images/items/MKDS_DK_Pass_Course_Icon.png",
    "Tick-Tock Clock": "images/items/MKDS_Tick-Tock_Clock_Course_Icon.png",
    "Mario Circuit": "images/items/MKDS_Mario_Circuit_Course_Icon.png",
    "Airship Fortress": "images/items/MKDS_Airship_Fortress_Course_Icon.png",
    "Wario Stadium": "images/items/MKDS_Wario_Stadium_Course_Icon.png",
    "Peach Gardens": "images/items/MKDS_Peach_Gardens_Course_Icon.png",
    "Bowser's Castle": "images/items/MKDS_Bowser_Castle_Course_Icon.png",
    "Rainbow Road": "images/items/MKDS_Rainbow_Road_Course_Icon.png",
    "SNES Mario Circuit 1": "images/items/MKDS_SNES_Mario_Circuit_1_Course_Icon.png",
    "N64 Moo Moo Farm": "images/items/MKDS_N64_Moo_Moo_Farm_Course_Icon.png",
    "GBA Peach Circuit": "images/items/MKDS_GBA_Peach_Circuit_Course_Icon.png",
    "GCN Luigi Circuit": "images/items/MKDS_GCN_Luigi_Circuit_Course_Icon.png",
    "SNES Donut Plains 1": "images/items/MKDS_SNES_Donut_Plains_1_Course_Icon.png",
    "N64 Frappe Snowland": "images/items/MKDS_N64_Frappe_Snowland_Course_Icon.png",
    "GBA Bowser Castle 2": "images/items/MKDS_GBA_Bowser_Castle_2_Course_Icon.png",
    "GCN Baby Park": "images/items/MKDS_GCN_Baby_Park_Course_Icon.png",
    "SNES Koopa Beach 2": "images/items/MKDS_SNES_Koopa_Beach_2_Course_Icon.png",
    "N64 Choco Mountain": "images/items/MKDS_N64_Choco_Mountain_Course_Icon.png",
    "GBA Luigi Circuit": "images/items/MKDS_GBA_Luigi_Circuit_Course_Icon.png",
    "GCN Mushroom Bridge": "images/items/MKDS_GCN_Mushroom_Bridge_Course_Icon.png",
    "SNES Choco Island 2": "images/items/MKDS_SNES_Choco_Island_2_Course_Icon.png",
    "N64 Banshee Boardwalk": "images/items/MKDS_N64_Banshee_Boardwalk_Course_Icon.png",
    "GBA Sky Garden": "images/items/MKDS_GBA_Sky_Garden_Course_Icon.png",
    "GCN Yoshi Circuit": "images/items/MKDS_GCN_Yoshi_Circuit_Course_Icon.png",
}

MISSION_ICON = {
    "Level 1 Mission 1 - Drive through 5 numbered gates in order": "images/items/1-1.PNG",
    "Level 1 Mission 2 - Collect all 15 coins": "images/items/1-2.PNG",
    "Level 1 Mission 3 - Destroy all 10 item boxes": "images/items/1-3.PNG",
    "Level 1 Mission 4 - Get the Star and use it to hit 5 Cheep Cheeps": "images/items/1-4.PNG",
    "Level 1 Mission 5 - Drive through 6 numbered gates in order": "images/items/1-5.PNG",
    "Level 1 Mission 6 - Drive out of the mansion, backward": "images/items/1-6.PNG",
    "Level 1 Mission 7 - Collect all 20 coins": "images/items/1-7.PNG",
    "Level 1 Mission 8 - Perform 4 power-slide turbo boosts in 1 lap": "images/items/1-8.PNG",
    "Level 1 Mission 9 - Boss - Big Bully": "images/items/MKDS_Big_Bully_Course_Icon.png",
    "Level 2 Mission 1 - Crash into and destroy all 10 wooden crates": "images/items/2-1.PNG",
    "Level 2 Mission 2 - Collect all 10 coins": "images/items/2-2.PNG",
    "Level 2 Mission 3 - Drive through 5 numbered gates in order": "images/items/2-3.PNG",
    "Level 2 Mission 4 - Destroy all 5 item boxes": "images/items/2-4.PNG",
    "Level 2 Mission 5 - Collect all 20 coins": "images/items/2-5.PNG",
    "Level 2 Mission 6 - Use Bob-ombs to destroy all 5 Pokeys": "images/items/2-6.PNG",
    "Level 2 Mission 7 - Drive through 10 numbered gates in order": "images/items/2-7.PNG",
    "Level 2 Mission 8 - Perform 6 power-slide turbo boosts in 3 laps": "images/items/2-8.PNG",
    "Level 2 Mission 9 - Boss - Eyerok": "images/items/MKDS_Eyerok_Course_Icon.png",
    "Level 3 Mission 1 - Destroy all 5 item boxes": "images/items/3-1.PNG",
    "Level 3 Mission 2 - Drive through 5 numbered gates in order, backward": "images/items/3-2.PNG",
    "Level 3 Mission 3 - Collect 15 coins while avoiding the Chain Chomp": "images/items/3-3.PNG",
    "Level 3 Mission 4 - Reach the finish before Yoshi": "images/items/3-4.PNG",
    "Level 3 Mission 5 - Drive through numbered gates in order": "images/items/3-5.PNG",
    "Level 3 Mission 6 - Hit Monty Moles with shells 5 times": "images/items/3-6.PNG",
    "Level 3 Mission 7 - Perform 10 power-slide turbo boosts in 1 lap": "images/items/3-7.PNG",
    "Level 3 Mission 8 - Collect all 20 coins": "images/items/3-8.PNG",
    "Level 3 Mission 9 - Boss - Goomboss": "images/items/MKDS_Goomboss_Course_Icon.png",
    "Level 4 Mission 1 - Reach the finish before Donkey Kong": "images/items/4-1.PNG",
    "Level 4 Mission 2 - Blast 20 crabs": "images/items/4-2.PNG",
    "Level 4 Mission 3 - Reach the finish before the red car": "images/items/4-3.PNG",
    "Level 4 Mission 4 - Drive through 7 numbered gates in order": "images/items/4-4.PNG",
    "Level 4 Mission 5 - Collect 15 coins without being squished by a Thwomp": "images/items/4-5.PNG",
    "Level 4 Mission 6 - Break 10 item boxes while avoiding the Fake Items": "images/items/4-6.PNG",
    "Level 4 Mission 7 - Drive through 10 gates": "images/items/4-7.PNG",
    "Level 4 Mission 8 - Perform 9 power-slide turbo boosts in 1 lap": "images/items/4-8.PNG",
    "Level 4 Mission 9 - Boss - King Boo": "images/items/MKDS_King_Boo_Course_Icon.png",
    "Level 5 Mission 1 - Reach the finish before the stray Chain Chomp": "images/items/5-1.PNG",
    "Level 5 Mission 2 - Drive backward and collect 15 coins without hitting a snowman": "images/items/5-2.PNG",
    "Level 5 Mission 3 - Destroy all 5 item boxes": "images/items/5-3.PNG",
    "Level 5 Mission 4 - Drive through 10 numbered gates in order": "images/items/5-4.PNG",
    "Level 5 Mission 5 - Complete 1 lap in the opposite direction within the time limit": "images/items/5-5.PNG",
    "Level 5 Mission 6 - Collect all 18 coins": "images/items/5-6.PNG",
    "Level 5 Mission 7 - Drive through 8 numbered gates in order": "images/items/5-7.PNG",
    "Level 5 Mission 8 - Reach the finish before Mario": "images/items/5-8.PNG",
    "Level 5 Mission 9 - Boss - Big Bob-omb": "images/items/MKDS_Big_Bob-omb_Course_Icon.png",
    "Level 6 Mission 1 - Drive backward across the spinning bridge without falling": "images/items/6-1.PNG",
    "Level 6 Mission 2 - Get Stars and run over 15 Rocky Wrenches": "images/items/6-2.PNG",
    "Level 6 Mission 3 - Collect all 20 coins": "images/items/6-3.PNG",
    "Level 6 Mission 4 - Destroy all 10 item boxes": "images/items/6-4.PNG",
    "Level 6 Mission 5 - Drive through 8 numbered gates in order": "images/items/6-5.PNG",
    "Level 6 Mission 6 - Perform 14 power-slide turbo boosts in 1 lap": "images/items/6-6.PNG",
    "Level 6 Mission 7 - Collect all 40 coins": "images/items/6-7.PNG",
    "Level 6 Mission 8 - Reach the finish before Peach": "images/items/6-8.PNG",
    "Level 6 Mission 9 - Boss - Chief Chilly": "images/items/MKDS_Chief_Chilly_Course_Icon.png",
    "Level 7 Mission 1 - Perform 6 power-slide turbo boosts in 1 lap": "images/items/7-1.PNG",
    "Level 7 Mission 2 - Reach the finish before Bowser": "images/items/7-2.PNG",
    "Level 7 Mission 3 - Complete 2 laps within the time limit": "images/items/7-3.PNG",
    "Level 7 Mission 4 - Use shells to defeat all 30 Goombas within the time limit": "images/items/7-4.PNG",
    "Level 7 Mission 5 - Collect all 20 coins": "images/items/7-5.PNG",
    "Level 7 Mission 6 - Drive through 8 numbered gates in order": "images/items/7-6.PNG",
    "Level 7 Mission 7 - Drive backward and collect all 12 coins without hitting a burner": "images/items/7-7.PNG",
    "Level 7 Mission 8 - Break all 10 item boxes while avoiding the Fake Items": "images/items/7-8.PNG",
    "Level 7 Mission 9 - Boss - Wiggler": "images/items/MKDS_Wiggler_Course_Icon.png",
}

# Cup "map pin" emblems for the cups_grid.png background (baked in - see build_map_images
# below). Every cup has a dedicated "_Emblem.png" except Flower Cup, whose wiki source only
# had an "_Icon.png" - both are circular, bordered artwork, not a mismatch in style.
CUP_ICON = {
    "Mushroom Cup": "images/items/MKDS_Mushroom_Cup_Emblem.png",
    "Flower Cup": "images/items/MKDS_Flower_Cup_Icon.png",
    "Star Cup": "images/items/MKDS_Star_Cup_Emblem.png",
    "Special Cup": "images/items/MKDS_Special_Cup_Emblem.png",
    "Shell Cup": "images/items/MKDS_Shell_Cup_Emblem.png",
    "Banana Cup": "images/items/MKDS_Banana_Cup_Emblem.png",
    "Leaf Cup": "images/items/MKDS_Leaf_Cup_Emblem.png",
    "Lightning Cup": "images/items/MKDS_Lightning_Cup_Emblem.png",
}

for _name in CHARACTERS:
    assert _name in CHAR_ICON, f"CHAR_ICON missing entry for {_name!r}"
for _name in KARTS:
    assert _name in KART_ICON, f"KART_ICON missing entry for {_name!r}"
for _name in TRACKS:
    assert _name in TRACK_ICON, f"TRACK_ICON missing entry for {_name!r}"
for _name in MISSIONS:
    assert _name in MISSION_ICON, f"MISSION_ICON missing entry for {_name!r}"
for _name in CUPS:
    assert _name in CUP_ICON, f"CUP_ICON missing entry for {_name!r}"

GENERIC_CHECKED_IMG = "images/items/track.png"


def _sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", name)


def character_code(name: str) -> str:
    return f"char_{_sanitize(name)}"


def kart_code(name: str) -> str:
    return f"kart_{_sanitize(name)}"


def track_code(name: str) -> str:
    return f"tt_{_sanitize(name)}"


def mission_code(index: int) -> str:
    level, mission = divmod(index, len(MISSION_OBJECTIVES_BY_LEVEL[0]))
    return f"mission_L{level + 1}M{mission + 1}"


def _toggle_item(name: str, img: str, code: str) -> dict:
    return {
        "type": "toggle",
        "name": name,
        "img": img,
        "disabled_img_mods": ["grey"],
        "codes": code,
    }


def _progress_overlay_item(name: str, img: str, code: str) -> dict:
    # No disabled_img_mods - always Active (forced visible in onClear/set_progress_overlay,
    # see autotracking.lua), it's a text carrier ("X/Y" via :SetOverlay), not itself a
    # locked/unlocked state.
    return {"type": "toggle", "name": name, "img": img, "codes": code}


def _progressive_item_3stage(name: str, real_icon: str, code: str) -> dict:
    # REDESIGNED 2026-08-07: was a 2-stage item (stage 0 = real icon shown unconditionally,
    # stage 1 = generic checked icon), which never showed a distinguishable "unlocked"
    # state at all - only "not yet checked" vs "checked" - see NOTES.md and this file's own
    # module docstring. Now 3 stages, mirroring how Cups' real PopTracker locations already
    # show locked/reachable/checked via access_rules: stage 0 (locked) is the real icon
    # GREYED OUT (img_mods, same "grey" mod toggle items already use for their disabled
    # state), stage 1 (unlocked, not yet completed) is the real icon at full color, stage 2
    # (completed) is the generic checked icon. Driven by TWO independent signals - item
    # RECEIVED (0 -> 1, via ITEM_NAME_TO_CODE/PROGRESSIVE_ITEM_CODES) and location CHECKED
    # (-> 2, via LOCATION_NAME_TO_ITEM_STAGE) - see autotracking.lua's onItemReceived/
    # onLocationChecked.
    return {
        "type": "progressive",
        "name": name,
        "initial_stage_idx": 0,
        "codes": code,
        "stages": [
            {"img": real_icon, "img_mods": ["grey"]},
            {"img": real_icon},
            {"img": GENERIC_CHECKED_IMG},
        ],
    }


def build_items() -> list[dict]:
    items = []
    items += [_toggle_item(name, CHAR_ICON[name], character_code(name)) for name in CHARACTERS]
    items += [_toggle_item(name, KART_ICON[name], kart_code(name)) for name in KARTS]
    items.append(_progress_overlay_item(
        "Cups Progress", "images/items/MKDS_Mushroom_Cup_Gold_Trophy.png", "progress_cups",
    ))
    items.append(_progress_overlay_item(
        "Time Trial Progress", TRACK_ICON[TRACKS[0]], "progress_time_trial",
    ))
    items.append(_progress_overlay_item(
        "Missions Progress", MISSION_ICON[MISSIONS[0]], "progress_missions",
    ))
    items += [
        _progressive_item_3stage(f"Time Trial - {track}", TRACK_ICON[track], track_code(track))
        for track in TRACKS
    ]
    items += [
        _progressive_item_3stage(mission, MISSION_ICON[mission], mission_code(i))
        for i, mission in enumerate(MISSIONS)
    ]
    return items


def _chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def build_layouts() -> dict:
    character_rows = _chunk([character_code(n) for n in CHARACTERS], 4)
    # 2 characters' worth (6 karts) per row - KARTS is already ordered 3-per-character
    # (see rom_addresses.KART_ID_TO_NAME), so this keeps that grouping visually obvious.
    kart_rows = _chunk([kart_code(n) for n in KARTS], 6)
    track_rows = _chunk([track_code(t) for t in TRACKS], 8)
    mission_rows = _chunk([mission_code(i) for i in range(len(MISSIONS))], len(MISSION_OBJECTIVES_BY_LEVEL[0]))

    return {
        "layouts/characters": {"type": "itemgrid", "item_size": "64,64", "rows": character_rows},
        "layouts/karts": {"type": "itemgrid", "item_size": "64,64", "rows": kart_rows},
        "layouts/top_left": {
            "type": "array",
            "orientation": "vertical",
            "content": [
                {"type": "layout", "key": "layouts/characters"},
                {"type": "layout", "key": "layouts/karts"},
            ],
        },
        "layouts/progress": {
            "type": "itemgrid",
            "item_size": "64,64",
            "rows": [["progress_cups", "progress_time_trial", "progress_missions"]],
        },
        "layouts/cups_map": {
            "type": "map", "maps": ["cups_map"], "max_width": CUPS_MAP_SIZE[0], "max_height": CUPS_MAP_SIZE[1],
        },
        "layouts/gp_placements_map": {
            "type": "map", "maps": ["gp_placements_map"],
            "max_width": GP_MAP_SIZE[0], "max_height": GP_MAP_SIZE[1],
        },
        "layouts/time_trial": {"type": "itemgrid", "item_size": "64,64", "rows": track_rows},
        "layouts/missions": {"type": "itemgrid", "item_size": "64,64", "rows": mission_rows},
        "layouts/main_tab": {
            "type": "array",
            "orientation": "vertical",
            "content": [
                {
                    "type": "array",
                    "orientation": "horizontal",
                    "content": [
                        {"type": "layout", "key": "layouts/top_left"},
                        {"type": "layout", "key": "layouts/cups_map"},
                        {"type": "layout", "key": "layouts/progress"},
                    ],
                },
                {"type": "layout", "key": "layouts/gp_placements_map"},
            ],
        },
        "layouts/tracks_missions_tab": {
            "type": "array",
            "orientation": "vertical",
            "content": [
                {"type": "layout", "key": "layouts/time_trial"},
                {"type": "layout", "key": "layouts/missions"},
            ],
        },
        "tracker_default": {
            "type": "tabbed",
            "tabs": [
                {"title": "Main", "content": {"type": "layout", "key": "layouts/main_tab"}},
                {"title": "Time Trial & Missions", "content": {"type": "layout", "key": "layouts/tracks_missions_tab"}},
            ],
        },
    }


# --- Cups / Grand Prix placements: real PopTracker locations+sections on generated grid
# maps (see build_map_images below for why - PopTracker's locations+sections system only
# renders through the map/pin system, no flat-grid location-checklist widget). Grid
# geometry is fixed (8 cups always 4x2, 32 tracks always 8x4 - MKDS's own roster sizes
# never change), not derived from item/location counts.

CUPS_MAP_COLS = 4
CUPS_MAP_COL_SPACING = 52
CUPS_MAP_ROW_SPACING = 86
CUPS_MAP_FIRST_X = 32
CUPS_MAP_FIRST_Y = 65
CUPS_MAP_SIZE = (220, 172)
CUP_ICON_SIZE = 40
# How far above each pin the baked-in emblem is centered (see build_map_images) - leaves
# room for the pin marker itself to render below the art, matching the original layout.
CUP_ICON_Y_OFFSET = 33

GP_MAP_COLS = 8
GP_MAP_COL_SPACING = 80
GP_MAP_ROW_SPACING = 80
GP_MAP_FIRST_X = 48
GP_MAP_FIRST_Y = 48
GP_MAP_SIZE = (656, 336)

MAP_BG_COLOR = (43, 46, 53, 255)


def build_cup_locations() -> list[dict]:
    locations = []
    for i, cup in enumerate(CUPS):
        row, col = divmod(i, CUPS_MAP_COLS)
        x = CUPS_MAP_FIRST_X + col * CUPS_MAP_COL_SPACING
        y = CUPS_MAP_FIRST_Y + row * CUPS_MAP_ROW_SPACING
        locations.append({
            "name": cup,
            "sections": [{"name": "Bronze"}, {"name": "Silver"}, {"name": "Win"}],
            "map_locations": [{"map": "cups_map", "x": x, "y": y}],
            "access_rules": [f"$mkds_cup_accessible|{cup}"],
        })
    return locations


def build_gp_track_locations() -> list[dict]:
    locations = []
    for i, track in enumerate(TRACKS):
        row, col = divmod(i, GP_MAP_COLS)
        x = GP_MAP_FIRST_X + col * GP_MAP_COL_SPACING
        y = GP_MAP_FIRST_Y + row * GP_MAP_ROW_SPACING
        locations.append({
            "name": track,
            "sections": [{"name": "3rd Place"}, {"name": "2nd Place"}, {"name": "1st Place"}],
            "map_locations": [{"map": "gp_placements_map", "x": x, "y": y}],
            "access_rules": [f"$mkds_track_accessible|{track}"],
            "chest_unopened_img": TRACK_ICON[track],
            "chest_opened_img": TRACK_ICON[track],
        })
    return locations


def build_maps() -> list[dict]:
    return [
        {
            "name": "cups_map", "location_size": 18, "location_border_thickness": 2,
            "img": "images/maps/cups_grid.png",
        },
        {
            "name": "gp_placements_map", "location_size": 64, "location_border_thickness": 2,
            "img": "images/maps/gp_placements_grid.png",
        },
    ]


def build_map_images() -> None:
    maps_dir = PACK_DIR / "images" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    # cups_grid.png: Cups have no per-location chest image field of their own (unlike GP
    # placements below), so their real emblem is baked directly into the map background,
    # above each pin - a workaround, not a PopTracker feature (mirrors the reference Mario
    # Kart Double Dash AP pack's own non-course-specific-check grid canvas - see README.md).
    cups_canvas = Image.new("RGBA", CUPS_MAP_SIZE, MAP_BG_COLOR)
    half = CUP_ICON_SIZE // 2
    for i, cup in enumerate(CUPS):
        row, col = divmod(i, CUPS_MAP_COLS)
        pin_x = CUPS_MAP_FIRST_X + col * CUPS_MAP_COL_SPACING
        pin_y = CUPS_MAP_FIRST_Y + row * CUPS_MAP_ROW_SPACING
        icon = Image.open(PACK_DIR / CUP_ICON[cup]).convert("RGBA")
        icon = icon.resize((CUP_ICON_SIZE, CUP_ICON_SIZE), Image.LANCZOS)
        paste_xy = (pin_x - half, pin_y - CUP_ICON_Y_OFFSET - half)
        cups_canvas.alpha_composite(icon, paste_xy)
    cups_canvas.save(maps_dir / "cups_grid.png")

    # gp_placements_grid.png: plain canvas, no baked art - each GP placement pin instead
    # uses its own chest_unopened_img/chest_opened_img (the real course icon) directly, a
    # native PopTracker feature Cups above don't have access to (no chest image field on a
    # plain location/section).
    gp_canvas = Image.new("RGBA", GP_MAP_SIZE, MAP_BG_COLOR)
    gp_canvas.save(maps_dir / "gp_placements_grid.png")


# --- Lua lookup table generation -----------------------------------------------------

def _lua_value(value) -> str:
    if value is True:
        return "true"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k} = {_lua_value(v)}" for k, v in value.items()) + "}"
    raise TypeError(f"unsupported Lua value: {value!r}")


def _lua_key(key) -> str:
    if isinstance(key, int):
        return f"[{key}]"
    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
    return f'["{escaped}"]'


def _write_lua_tables(path: Path, header: str, tables: dict[str, dict]) -> None:
    lines = [f"-- {path.name} (generated by generate_pack.py - do not hand-edit)", "--"]
    lines += [f"-- {line}" for line in header.splitlines()]
    for table_name, mapping in tables.items():
        lines.append("")
        lines.append(f"{table_name} = {{")
        for key, value in mapping.items():
            lines.append(f"    {_lua_key(key)} = {_lua_value(value)},")
        lines.append("}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    items = build_items()
    (PACK_DIR / "items" / "items.json").write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")

    layouts = build_layouts()
    (PACK_DIR / "layouts" / "layouts.json").write_text(json.dumps(layouts, indent=2) + "\n", encoding="utf-8")

    cup_locations = build_cup_locations()
    (PACK_DIR / "locations" / "cups.json").write_text(json.dumps(cup_locations, indent=2) + "\n", encoding="utf-8")

    gp_locations = build_gp_track_locations()
    (PACK_DIR / "locations" / "grandPrixTracks.json").write_text(
        json.dumps(gp_locations, indent=2) + "\n", encoding="utf-8",
    )

    maps = build_maps()
    (PACK_DIR / "maps" / "maps.json").write_text(json.dumps(maps, indent=2) + "\n", encoding="utf-8")

    build_map_images()

    # ITEM_NAME_TO_CODE: keyed by the real, BARE AP item name (as received via
    # Archipelago:AddItemHandler's item_name argument) - NOT the location-suffixed name,
    # and NOT Cups (handled separately by name via CUP_NAME_SET - see cup_accessibility.lua
    # below - since Cups have no items.json entry of their own). Time Trial/Mission unlock
    # items ARE covered here (2026-08-07 - see _progressive_item_3stage's docstring above);
    # PROGRESSIVE_ITEM_CODES (below) tells autotracking.lua's onItemReceived which of these
    # codes need CurrentStage bumped instead of a plain .Active = true.
    item_name_to_code = {}
    for name in CHARACTERS:
        item_name_to_code[name] = character_code(name)
    for name in KARTS:
        item_name_to_code[name] = kart_code(name)
    for name in TRACKS:
        item_name_to_code[name] = track_code(name)
    for i, name in enumerate(MISSIONS):
        item_name_to_code[name] = mission_code(i)
    _write_lua_tables(
        PACK_DIR / "scripts" / "item_name_to_code.lua",
        "Maps a received AP item's bare name to its items.json tracker code. Covers\n"
        "Characters, Karts, and Time Trial/Mission unlock items (all real, individually-\n"
        "named AP items - see worlds/mkds/items.py). Cups are NOT here - they're tracked\n"
        "purely in Lua via cup_accessibility.lua's CUP_NAME_SET, since Cups have no\n"
        "items.json entry of their own (real PopTracker locations instead - see\n"
        "location_section_mapping.lua). The filler \"Green Flag\" and anything else\n"
        "unrecognized is deliberately absent - onItemReceived treats a missing lookup as\n"
        "a no-op.",
        {"ITEM_NAME_TO_CODE": item_name_to_code},
    )

    # PROGRESSIVE_ITEM_CODES: which ITEM_NAME_TO_CODE codes are 3-stage progressive items
    # (Time Trial/Missions) rather than simple 2-state toggles (Characters/Karts) - tells
    # autotracking.lua's onItemReceived/onClear whether to set .CurrentStage or .Active.
    progressive_codes = {track_code(t): True for t in TRACKS}
    progressive_codes.update({mission_code(i): True for i in range(len(MISSIONS))})
    _write_lua_tables(
        PACK_DIR / "scripts" / "progressive_item_codes.lua",
        "Which ITEM_NAME_TO_CODE codes are 3-stage progressive items (Time Trial/\n"
        "Missions) rather than simple 2-state toggles (Characters/Karts) - tells\n"
        "autotracking.lua's onItemReceived/onClear whether to advance .CurrentStage or\n"
        "flip .Active.",
        {"PROGRESSIVE_ITEM_CODES": progressive_codes},
    )

    # cup_accessibility.lua: CUP_NAME_SET (onItemReceived recognizes a received Cup unlock
    # item by name) and TRACK_TO_CUP (a track's own GP-placement accessibility mirrors its
    # parent cup's) - see autotracking.lua's mkds_cup_accessible/mkds_track_accessible.
    cup_name_set = {cup: True for cup in CUPS}
    track_to_cup = {}
    for cup, cup_tracks in TRACKS_BY_CUP.items():
        for track in cup_tracks:
            track_to_cup[track] = cup
    _write_lua_tables(
        PACK_DIR / "scripts" / "cup_accessibility.lua",
        "CUP_NAME_SET: cup name -> true, for onItemReceived to recognize a received cup\n"
        "unlock item (worlds/mkds's own individually-named Cup item - see rules.py's\n"
        "module docstring). TRACK_TO_CUP: track name -> its parent cup's name, so a\n"
        "track's own GP-placement accessibility can mirror its cup's - see\n"
        "autotracking.lua's mkds_cup_accessible/mkds_track_accessible.",
        {"CUP_NAME_SET": cup_name_set, "TRACK_TO_CUP": track_to_cup},
    )

    # location_section_mapping.lua: Cups + Grand Prix placements (the two categories using
    # real PopTracker locations+sections) - checked-location name/id -> {location, section}.
    location_name_to_section = {}
    for cup in CUPS:
        for section in ("Bronze", "Silver", "Win"):
            location_name_to_section[f"{cup} - {section}"] = {"location": cup, "section": section}
    for track in TRACKS:
        for section in ("3rd Place", "2nd Place", "1st Place"):
            location_name_to_section[f"{track} - {section}"] = {"location": track, "section": section}
    location_id_to_section = {
        location_table[name].code: value for name, value in location_name_to_section.items()
    }
    _write_lua_tables(
        PACK_DIR / "scripts" / "location_section_mapping.lua",
        "Maps a checked AP location's name/id to {location=<PopTracker location name>,\n"
        "section=<section name>} for Cups + Grand Prix placements (the two categories\n"
        "still using real PopTracker locations+sections) - autotracking.lua builds the\n"
        "address string \"@\" .. location .. \"/\" .. section and resolves it via\n"
        "Tracker:FindObjectForCode. LOCATION_ID_TO_SECTION is the same data keyed by the\n"
        "location's numeric AP code, used to resync Archipelago.CheckedLocations after a\n"
        "reconnect (location events carry a name, but CheckedLocations is id-only).",
        {"LOCATION_NAME_TO_SECTION": location_name_to_section, "LOCATION_ID_TO_SECTION": location_id_to_section},
    )

    # location_item_stage_mapping.lua: Time Trial/Mission COMPLETION only (the "- Staff
    # Ghost Beaten"/"- Clear" top-tier location) -> {code, stage=2} (the 3rd, completed
    # stage - see _progressive_item_3stage's docstring above; stage 0->1 is driven by the
    # matching AP item instead, via ITEM_NAME_TO_CODE/PROGRESSIVE_ITEM_CODES).
    location_name_to_item_stage = {}
    for track in TRACKS:
        location_name_to_item_stage[f"{track} - Staff Ghost Beaten"] = {"code": track_code(track), "stage": 2}
    for i, mission in enumerate(MISSIONS):
        location_name_to_item_stage[f"{mission} - Clear"] = {"code": mission_code(i), "stage": 2}
    location_id_to_item_stage = {
        location_table[name].code: value for name, value in location_name_to_item_stage.items()
    }
    _write_lua_tables(
        PACK_DIR / "scripts" / "location_item_stage_mapping.lua",
        "Maps a checked AP location's name/id to {code=<items.json progressive item\n"
        "code>, stage=<target CurrentStage>} for Time Trial/Missions' COMPLETION signal\n"
        "only - these two categories are items.json progressive items (see\n"
        "generate_pack.py's module docstring for why), not real PopTracker locations, so\n"
        "they're driven by directly setting .CurrentStage instead of a section's\n"
        ".AvailableChestCount. LOCATION_ID_TO_ITEM_STAGE is the same data keyed by the\n"
        "location's numeric AP code, used to resync Archipelago.CheckedLocations after a\n"
        "reconnect.",
        {
            "LOCATION_NAME_TO_ITEM_STAGE": location_name_to_item_stage,
            "LOCATION_ID_TO_ITEM_STAGE": location_id_to_item_stage,
        },
    )

    # progress_categories.lua: AP location name/id -> progress category ("cups"/
    # "time_trial"/"missions") for exactly the TOP-TIER locations (cup "- Win", track
    # "- Staff Ghost Beaten", mission "- Clear") - drives the progress_cups/
    # progress_time_trial/progress_missions "X/Y" counters via CHECKED locations (not
    # received items - see NOTES.md's "fifth redesign pass" on why Trophy items were
    # removed entirely) - see autotracking.lua's onLocationChecked/onClear.
    location_name_to_progress_category = {}
    for cup in CUPS:
        location_name_to_progress_category[f"{cup} - Win"] = "cups"
    for track in TRACKS:
        location_name_to_progress_category[f"{track} - Staff Ghost Beaten"] = "time_trial"
    for mission in MISSIONS:
        location_name_to_progress_category[f"{mission} - Clear"] = "missions"
    location_id_to_progress_category = {
        location_table[name].code: category for name, category in location_name_to_progress_category.items()
    }
    _write_lua_tables(
        PACK_DIR / "scripts" / "progress_categories.lua",
        "Maps a checked AP location's name/id to its progress category (\"cups\"/\n"
        "\"time_trial\"/\"missions\") for exactly the top-tier locations - drives the\n"
        "progress_cups/progress_time_trial/progress_missions \"X/Y\" counters. Every\n"
        "cup/track/mission is always a real AP location whenever its category is active\n"
        "at all (worlds/mkds's own \"any N of M\" design), so a checked top-tier location\n"
        "always counts, unconditionally.",
        {
            "LOCATION_NAME_TO_PROGRESS_CATEGORY": location_name_to_progress_category,
            "LOCATION_ID_TO_PROGRESS_CATEGORY": location_id_to_progress_category,
        },
    )

    print(
        f"Pack generation complete.\n"
        f"  {len(items)} items.json entries\n"
        f"  {len(cup_locations) + len(gp_locations)} locations "
        f"({sum(len(loc['sections']) for loc in cup_locations + gp_locations)} sections)"
    )


if __name__ == "__main__":
    main()
