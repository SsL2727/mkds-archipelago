# regions.py
#
# Region graph for the Mario Kart DS world. Kept deliberately simple: Menu -> three
# top-level regions (Grand Prix, Time Trial, Mission Mode), each holding whichever
# locations are goal-required for this seed (see rules.py for how that subset is chosen -
# per Instructions.txt, only goal-required content is part of the AP economy at all;
# everything else stays vanilla and isn't represented here as a location - not just
# "unconditionally accessible", genuinely absent from the region graph. This matters for
# fill: create_items() only sizes the pool to len(required_locations), so a non-required
# location instantiated here with nothing to put in it would make the seed unfillable).
#
# TODO: this assumes access logic (which cups/missions/time-trials are currently
# reachable given received Progressive items) lives entirely in rules.py's location
# access rules rather than in the region graph itself (no per-cup sub-regions). Revisit
# if that turns out to be too coarse once client.py needs to reason about "what should
# currently be selectable in-game" for forcing menu state.

from BaseClasses import Location, Region
from .locations import location_table


class MKDSLocation(Location):
    game: str = "Mario Kart DS"


def create_regions(world) -> None:
    player = world.player
    multiworld = world.multiworld
    required_locations = world.required_locations  # set by decide_goal_requirements() in generate_early

    menu = Region("Menu", player, multiworld)
    grand_prix = Region("Grand Prix", player, multiworld)
    time_trial = Region("Time Trial", player, multiworld)
    mission_mode = Region("Mission Mode", player, multiworld)

    multiworld.regions.append(menu)
    multiworld.regions.append(grand_prix)
    multiworld.regions.append(time_trial)
    multiworld.regions.append(mission_mode)

    menu.connect(grand_prix)
    menu.connect(time_trial)
    menu.connect(mission_mode)

    region_by_name = {
        "Grand Prix": grand_prix,
        "Time Trial": time_trial,
        "Mission Mode": mission_mode,
    }

    for name, data in location_table.items():
        if name not in required_locations:
            continue  # not needed for this seed's goal - stays vanilla, not an AP location at all
        region = region_by_name.get(data.region, menu)
        location = MKDSLocation(player, name, data.code, region)
        region.locations.append(location)
