# rules.py
#
# Goal-scoping and access rules. Per Instructions.txt: only cups/races/time-trials/
# missions actually needed for the selected goal are real AP locations (item-gated,
# send checks); everything else stays vanilla and isn't represented here. For "a
# selected number of X" goals, the specific required subset is chosen at generation
# time (not left open for the player to satisfy with any combination during play).
#
# All three goal legs (cups, time trials, missions) are implemented. Cups and Time
# Trials are item-gated: each required cup/track (after the first, which is free - see
# below) has its own item named directly after it (e.g. holding "Special Cup" unlocks
# Special Cup) - items.py has the full reasoning for why this replaced an earlier
# generic counted "Progressive Cup"/"Progressive Time Trial" design. Missions are NOT
# item-gated - there's no mission-unlock item at all (see items.py) because Randomize
# Mission Mode only shuffles WHICH mission occupies each slot, it doesn't gate access
# to Mission Mode itself, so mission locations always use an unconditional access rule
# regardless of whether they're goal-required (matching how non-required locations of
# every category are handled - required-ness only controls whether a location is real,
# i.e. sends a check, not whether it's reachable).

from worlds.generic.Rules import set_rule
from .options import Goal, RandomizeMissionMode
from .locations import CUPS, TRACKS, TRACKS_BY_CUP, MISSIONS


def choose_goal_required_cups(world) -> list[str]:
    """Return the required cups IN UNLOCK ORDER (index 0 is free/needs no item; each
    other index is unlocked by receiving the item named directly after it - see
    _sequence_access_rule below). Order is randomized per-seed for cups_all too, not
    just cups_count/combination - Instructions.txt establishes cup unlock order is
    always randomized regardless of the Randomize Cups sub-option chosen.
    """
    options = world.options
    goal = options.goal.value

    if goal == Goal.option_cups_all:
        chosen = list(CUPS)
    elif goal == Goal.option_cups_count:
        count = min(options.required_cup_count.value, len(CUPS))
        chosen = world.random.sample(CUPS, k=count)
    elif goal == Goal.option_combination and options.required_cup_count.value:
        count = min(options.required_cup_count.value, len(CUPS))
        chosen = world.random.sample(CUPS, k=count)
    else:
        chosen = []

    world.random.shuffle(chosen)
    return chosen


def choose_goal_required_time_trials(world) -> list[str]:
    """Return the required Time Trial tracks IN UNLOCK ORDER, mirroring
    choose_goal_required_cups exactly (same progressive-item pattern - see
    RandomizeTimeTrial's docstring in options.py). Empty if Time Trial isn't active or
    isn't part of the goal.
    """
    options = world.options
    goal = options.goal.value

    if not options.randomize_time_trial:
        return []

    if goal == Goal.option_time_trials_all:
        chosen = list(TRACKS)
    elif goal == Goal.option_time_trials_count:
        count = min(options.required_time_trial_count.value, len(TRACKS))
        chosen = world.random.sample(TRACKS, k=count)
    elif goal == Goal.option_combination and options.required_time_trial_count.value:
        count = min(options.required_time_trial_count.value, len(TRACKS))
        chosen = world.random.sample(TRACKS, k=count)
    else:
        chosen = []

    world.random.shuffle(chosen)
    return chosen


def choose_goal_required_missions(world) -> list[str]:
    """Return the required missions. Unordered (unlike cups/time trials) - missions
    aren't item-gated, so there's no "unlock order" for them to begin with, see module
    docstring. Empty if Mission Mode isn't active or isn't part of the goal.
    """
    options = world.options
    goal = options.goal.value

    if options.randomize_mission_mode.value == RandomizeMissionMode.option_off:
        return []

    if goal == Goal.option_mission_mode_complete:
        return list(MISSIONS)
    elif goal == Goal.option_missions_count:
        count = min(options.required_mission_count.value, len(MISSIONS))
        return world.random.sample(MISSIONS, k=count)
    elif goal == Goal.option_combination and options.required_mission_count.value:
        count = min(options.required_mission_count.value, len(MISSIONS))
        return world.random.sample(MISSIONS, k=count)
    return []


def decide_goal_requirements(world) -> None:
    """Must run in generate_early(), before create_items()/set_rules() - both need this
    already-decided so item-pool size and access rules agree with each other. AP's
    lifecycle order is generate_early -> create_regions -> create_items -> set_rules
    (see docs/world api.md), so this can't just live inside set_rules() like a simpler
    single-consumer value could.
    """
    world.required_cups_in_order = choose_goal_required_cups(world)
    world.required_time_trials_in_order = choose_goal_required_time_trials(world)
    world.required_missions = choose_goal_required_missions(world)

    # Per Instructions.txt, individual RACE wins are their own check-granting category
    # alongside cup wins ("finishing first in any race... each track can only give one
    # check" - races counted separately from cups in the item-count formula too). Every
    # track within a required cup becomes a required "{track} - 1st Place" location -
    # this is about earning checks along the way, not an extra completion requirement;
    # the completion condition below still only cares about cup WINS, not every
    # individual race within them (you don't need a perfect run to win a cup overall).
    world.required_race_tracks = {
        track
        for cup in world.required_cups_in_order
        for track in TRACKS_BY_CUP[cup]
    }
    # TODO: uses the fixed vanilla TRACKS_BY_CUP regardless of the Randomize Cups option
    # (unrandomized / tracks_random_no_overlap / tracks_random_with_overlap) - cup-track
    # shuffling isn't implemented anywhere yet (no code applies it to the actual in-game
    # cup contents), so this is correct for "unrandomized" (the default) and simply not
    # yet extended for the other two modes. Not a regression - genuinely unimplemented
    # everywhere else in the codebase too, just newly relevant now that this function
    # needs SOME track-per-cup mapping to work from. Revisit together with whatever
    # eventually implements real cup-track shuffling.

    world.required_locations = (
        {f"{cup} - Win" for cup in world.required_cups_in_order}
        | {f"{track} - 1st Place" for track in world.required_race_tracks}
        | {f"{track} - Staff Ghost Beaten" for track in world.required_time_trials_in_order}
        | {f"{mission} - Clear" for mission in world.required_missions}
        | {f"{mission} - 3 Stars" for mission in world.required_missions}
    )


def _sequence_access_rule(sequence: list[str], position: int, player: int):
    """Access rule for the location(s) tied to `sequence[position]` (a required cup or
    Time Trial track, in generation-time unlock order). Position 0 is always freely
    accessible - the bootstrap entry point into the chain (matches "you always have
    somewhere to start"). Every other position needs its own directly-named item
    (sequence[position] itself, e.g. "Special Cup") to have been received - see
    items.py's header comment for the full reasoning behind naming items this way.
    """
    if position == 0:
        return lambda state: True
    name = sequence[position]
    return lambda state, n=name: state.has(n, player)


def set_rules(world) -> None:
    player = world.player
    multiworld = world.multiworld
    required_cups_in_order = world.required_cups_in_order
    required_time_trials_in_order = world.required_time_trials_in_order
    required_missions = world.required_missions
    required_locations = world.required_locations
    track_to_required_cup = {
        track: cup
        for cup in required_cups_in_order
        for track in TRACKS_BY_CUP[cup]
    }

    # regions.py only instantiates locations that are in required_locations (everything
    # else stays vanilla and was never created as an AP location at all) - so every name
    # reachable via multiworld.get_location() here is already goal-required by
    # construction, no need to re-check membership.
    for name in required_locations:
        location = multiworld.get_location(name, player)

        if name.endswith(" - Win") and name[:-len(" - Win")] in required_cups_in_order:
            cup = name[:-len(" - Win")]
            position = required_cups_in_order.index(cup)
            set_rule(location, _sequence_access_rule(required_cups_in_order, position, player))
        elif name.endswith(" - 1st Place") and name[:-len(" - 1st Place")] in track_to_required_cup:
            # Individual race win - gated by the SAME access rule as its parent cup (you
            # need the cup unlocked to attempt any of its 4 tracks; which specific track
            # you win doesn't grant further progression on its own, see module docstring).
            cup = track_to_required_cup[name[:-len(" - 1st Place")]]
            position = required_cups_in_order.index(cup)
            set_rule(location, _sequence_access_rule(required_cups_in_order, position, player))
        elif name.endswith(" - Staff Ghost Beaten") and name[:-len(" - Staff Ghost Beaten")] in required_time_trials_in_order:
            track = name[:-len(" - Staff Ghost Beaten")]
            position = required_time_trials_in_order.index(track)
            set_rule(location, _sequence_access_rule(required_time_trials_in_order, position, player))
        else:
            # Required mission locations ("- Clear" / "- 3 Stars") land here too - no
            # item gates Mission Mode access, see module docstring.
            set_rule(location, lambda state: True)

    # NOTE: these are the LOGICAL/generation-time completion conditions (used by AP's own
    # solver, hints, etc.) - they say the seed is "beatable" once the player has received
    # every required cup/track's own unlock item (and, for missions, once the always-open
    # mission locations are simply reachable - there's no item gate to check, see module
    # docstring). This is deliberately NOT the same thing as the real-time trigger that
    # actually ends the player's game: that comes from client.py's game_watcher
    # (_check_goal_complete) sending a StatusUpdate with ClientStatus.CLIENT_GOAL once
    # every required LOCATION is server-confirmed checked - implemented and live-tested
    # 2026-08-04, see client.py/NOTES.md. Each leg here is only added if that category
    # actually has required content - the choose_goal_required_* functions already
    # return an empty list/collection when a category isn't part of the selected goal,
    # so no further goal-type check is needed here.
    # Each condition is "can the player logically reach every required location in this
    # category" - consistent across all three categories.
    conditions = []
    if required_cups_in_order:
        cup_locations = [f"{cup} - Win" for cup in required_cups_in_order]
        conditions.append(lambda state: all(state.can_reach_location(loc, player) for loc in cup_locations))
    if required_time_trials_in_order:
        tt_locations = [f"{track} - Staff Ghost Beaten" for track in required_time_trials_in_order]
        conditions.append(lambda state: all(state.can_reach_location(loc, player) for loc in tt_locations))
    if required_missions:
        mission_locations = [f"{mission} - Clear" for mission in required_missions] + \
            [f"{mission} - 3 Stars" for mission in required_missions]
        conditions.append(lambda state: all(state.can_reach_location(loc, player) for loc in mission_locations))

    if conditions:
        multiworld.completion_condition[player] = lambda state: all(condition(state) for condition in conditions)
