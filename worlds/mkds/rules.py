# rules.py
#
# Goal-scoping and access rules.
#
# REDESIGNED 2026-08-06, per user direction: "all items from categories that include at
# least one location must be accessible" - e.g. even when required_time_trial_count is
# just 1, all 32 Time Trial tracks must be accessible and give a check, not only a
# pre-chosen subset sized to that count. This applies to all three goal-scoped
# categories (Cups, Time Trials, Missions): whenever a category is part of the goal at
# all, EVERY cup/track/mission in it becomes a real AP location - the player picks freely
# which ones to actually go complete. This retired the OLDEST design entirely: choosing a
# specific subset in generation-time unlock order, item-gating each entry sequentially
# (position 0 free, every other position needing its own directly-named item).
#
# REDESIGNED AGAIN 2026-08-06 (second pass), per direct user feedback: "the new apworld
# starts with everything unlocked. The player should only start with either 1 cup, time
# trial, or mission." Every cup/track/mission in an active category is still a real
# location - only the STARTING reachability changed. Each ACTIVE category independently
# gets exactly ONE randomly-chosen bootstrap location reachable with zero items
# (choose_category_bootstrap below, mirroring choose_character_unlock_order/
# choose_kart_unlock_order's own "random position, no item needed" pattern) - every OTHER
# location in that category requires an unlock.
#
# REDESIGNED A THIRD TIME 2026-08-06: "don't unlock everything at once through one item.
# Each time trial and mission should be unlocked individually." REDESIGNED A FOURTH TIME
# 2026-08-06: "Cups should also be unlocked individually along with drivers and karts.
# Everything should be unlocked individually." Every cup/track/mission gets its own
# directly-named Progression item (items.py's CUP_UNLOCK_NAMES/TRACK_UNLOCK_NAMES/
# MISSION_UNLOCK_NAMES - literally the cup/track/mission's own name) - the bootstrap
# entry needs no item, every OTHER entry needs its own, exactly mirroring
# choose_character_unlock_order/choose_kart_unlock_order's own "one free by name, the
# rest individually named" pattern. Unconditional, no capacity fallback needed for any of
# the three categories (see items.py's module docstring for the capacity math) - an
# earlier version of this redesign had a more elaborate per-category "individual vs
# shared-Key vs fully-open" capacity solver (decide_unlock_modes, since removed) that
# existed only to make room for a since-removed Trophy item (see the fifth pass below) -
# without that competing for space, every category's own (M - 1) individual-unlock
# demand always fits its own M real locations, so there's nothing left to solve for.
#
# REDESIGNED A FIFTH TIME 2026-08-06, per direct user direction, removing a real design
# flaw: "I do not want any item that counts towards the goal. The only thing that counts
# towards the goal is complete the cup, time trial, or mission." completion_condition
# below no longer counts a received fungible "Trophy" item (items.py's now-removed
# CUP_TROPHY_NAME/etc) - it directly checks whether the REQUIRED locations themselves
# (each category's own "- Win"/"- Staff Ghost Beaten"/"- Clear" locations) are reachable,
# so completing the goal genuinely requires completing that many cups/tracks/missions
# yourself, not just receiving N interchangeable Trophy copies the fill algorithm could
# have placed at any unrelated check (including someone else's world). This IS a
# logically stronger condition than the real "any N of M, your choice which" goal
# (it requires ALL required entries reachable, not just N of them reachable) - AP's own
# solver has no way to represent "the player will choose to stop after N" at the pure
# logic-state level (state has no concept of "the player decided not to visit this
# location"), so this errs toward requiring more than strictly necessary rather than
# less; the REAL "stop as soon as N of them are actually completed" enforcement lives
# entirely in client.py's real-time _check_goal_complete, which reads the live server's
# ctx.checked_locations directly rather than any item count.
#
# Individual RACE placements (per-track 3rd/2nd/1st Place, added 2026-08-06) and cup
# Silver/Bronze tiers (also 2026-08-06) remain bonus-only, same as before: they grant
# checks along the way but never affect completion_condition, which only cares about
# each category's TOP-tier locations (cup Gold wins, Staff Ghosts beaten, missions
# cleared). A track's placement locations share their parent cup's own access rule
# (bootstrap-cup's tracks are free too; every other cup's tracks need that same cup's own
# unlock item) - Grand Prix placements aren't a separately-gated category of their own,
# matching how required_race_tracks has always been derived purely from
# required_cups_in_order.
#
# DESIGN CHANGE (see client.py/items.py): the world can no longer restrict what's
# selectable in-game at all (an ASM-patch investigation to suppress vanilla's baseline
# access failed - see NOTES_ARCHIVE.md) - it forces everything unlocked instead, and
# every Cup/Race/Time Trial check now additionally requires the character AND kart
# actually used to have been legitimately received as items (client.py's runtime check,
# not this module) - Mission checks dropped that requirement 2026-08-06 (Mission Mode's
# character/kart are game-determined per mission, not player-chosen, so there's nothing
# to legitimize - see client.py's _check_mission_result). Neither Characters nor Karts
# get an access rule here - unlike Cups/Time Trials/Missions, neither ever gates a
# LOCATION's reachability, only whether client.py honors the check it produces - so
# character/kart sequencing (choose_character_unlock_order/choose_kart_unlock_order
# below) only feeds items.py's pool and client.py's live check, never this module's
# access rules. This is a wholly separate mechanic from today's redesign and unaffected
# by it.

from typing import Optional

from worlds.generic.Rules import set_rule
from .options import Goal
from .items import CHARACTERS, KARTS
from .locations import CUPS, TRACKS, TRACKS_BY_CUP, MISSIONS


def choose_goal_required_cups(world) -> tuple[list[str], int]:
    """Returns (active_cups, win_target). active_cups is ALL 8 cups if Cups are part of
    the goal at all, else [] - every cup is always accessible/checkable whenever cups
    matter for the goal, not a pre-chosen subset (see module docstring). win_target is
    the number of GOLD cup wins actually needed to satisfy the goal (used by
    completion_condition below) - all 8 for cups_all, else the configured
    required_cup_count.
    """
    options = world.options
    goal = options.goal.value

    if goal == Goal.option_cups_all:
        return list(CUPS), len(CUPS)
    if goal == Goal.option_cups_count:
        return list(CUPS), min(options.required_cup_count.value, len(CUPS))
    if goal == Goal.option_combination and options.required_cup_count.value:
        return list(CUPS), min(options.required_cup_count.value, len(CUPS))
    return [], 0


def choose_goal_required_time_trials(world) -> tuple[list[str], int]:
    """Returns (active_tracks, win_target), mirroring choose_goal_required_cups exactly.
    Empty/0 if Time Trial isn't active or isn't part of the goal.
    """
    options = world.options
    goal = options.goal.value

    if not options.randomize_time_trial:
        return [], 0

    if goal == Goal.option_time_trials_all:
        return list(TRACKS), len(TRACKS)
    if goal == Goal.option_time_trials_count:
        return list(TRACKS), min(options.required_time_trial_count.value, len(TRACKS))
    if goal == Goal.option_combination and options.required_time_trial_count.value:
        return list(TRACKS), min(options.required_time_trial_count.value, len(TRACKS))
    return [], 0


def choose_goal_required_missions(world) -> tuple[list[str], int]:
    """Returns (active_missions, win_target), mirroring choose_goal_required_cups/
    _time_trials exactly. Empty/0 if Mission Mode isn't active or isn't part of the goal.
    """
    options = world.options
    goal = options.goal.value

    if not options.randomize_mission_mode:
        return [], 0

    if goal == Goal.option_mission_mode_complete:
        return list(MISSIONS), len(MISSIONS)
    if goal == Goal.option_missions_count:
        return list(MISSIONS), min(options.required_mission_count.value, len(MISSIONS))
    if goal == Goal.option_combination and options.required_mission_count.value:
        return list(MISSIONS), min(options.required_mission_count.value, len(MISSIONS))
    return [], 0


def choose_character_unlock_order(world) -> list[str]:
    """Return all 12 characters in per-seed randomized unlock order (index 0 is the
    seed's free starting character; every other index needs its own directly-named item
    - see client.py's _is_run_legitimate). Unlike the three functions above, this isn't
    goal-scoped - characters aren't tied to a specific goal type, they're either fully in
    the economy (all 12, when Randomize Characters is on) or not part of it at all.
    Empty if Randomize Characters is off.
    """
    if not world.options.randomize_characters:
        return []
    order = list(CHARACTERS)
    world.random.shuffle(order)
    return order


def choose_kart_unlock_order(world) -> list[str]:
    """Return all 36 real karts in per-seed randomized unlock order (index 0 is the
    seed's free starting kart, checked by name only - see client.py's
    _is_run_legitimate; every other index is a one-copy Useful item, same trimming
    treatment as Characters - see __init__.create_items()). Mirrors
    choose_character_unlock_order exactly and for the same reason: not goal-scoped, and
    - unlike cups/tracks/missions - never referenced by this module's access rules.
    Empty if Randomize Karts is off.
    """
    if not world.options.randomize_karts:
        return []
    order = list(KARTS)
    world.random.shuffle(order)
    return order


def choose_category_bootstrap(world, active_list: list[str]) -> Optional[str]:
    """Returns one randomly-chosen entry from active_list to serve as that category's
    zero-item-reachable bootstrap location this seed, or None if the category isn't
    active at all (empty list - matches choose_goal_required_cups/_time_trials/_missions'
    own empty-list-means-inactive convention). Every OTHER entry in the category instead
    requires its own individually-named unlock item - see set_rules.
    """
    if not active_list:
        return None
    return world.random.choice(active_list)


def decide_goal_requirements(world) -> None:
    """Must run in generate_early(), before create_items()/set_rules() - both need this
    already-decided so item-pool size and access rules agree with each other. AP's
    lifecycle order is generate_early -> create_regions -> create_items -> set_rules
    (see docs/world api.md), so this can't just live inside set_rules() like a simpler
    single-consumer value could.
    """
    world.required_cups_in_order, world.required_cup_win_count = choose_goal_required_cups(world)
    world.required_time_trials_in_order, world.required_time_trial_win_count = choose_goal_required_time_trials(world)
    world.required_missions_in_order, world.required_mission_win_count = choose_goal_required_missions(world)
    world.character_unlock_order = choose_character_unlock_order(world)
    world.kart_unlock_order = choose_kart_unlock_order(world)

    world.cup_bootstrap = choose_category_bootstrap(world, world.required_cups_in_order)
    world.time_trial_bootstrap = choose_category_bootstrap(world, world.required_time_trials_in_order)
    world.mission_bootstrap = choose_category_bootstrap(world, world.required_missions_in_order)

    # Per Instructions.txt, individual RACE placements are their own check-granting
    # category alongside cup wins ("finishing first in any race... each track can only
    # give one check" - races counted separately from cups in the item-count formula
    # too). Every track within an active cup becomes THREE bonus locations - "{track} -
    # 3rd/2nd/1st Place" (2026-08-06: finishing 3rd or better earns the 3rd Place check,
    # 2nd or better ALSO earns 2nd Place, 1st ALSO earns 1st Place - cumulative, see
    # client.py's _check_race_result) - this is about earning checks along the way, not
    # an extra completion requirement; completion_condition below only cares about cup
    # GOLD wins, not any individual race within them.
    world.required_race_tracks = {
        track
        for cup in world.required_cups_in_order
        for track in TRACKS_BY_CUP[cup]
    }
    # Cup-to-track assignment is always vanilla (Randomize Cups' track-shuffling modes
    # were removed - see options.py) - TRACKS_BY_CUP is simply correct here, not a
    # placeholder pending a shuffling feature that no longer exists.

    world.required_locations = (
        {f"{cup} - Win" for cup in world.required_cups_in_order}
        | {f"{cup} - Silver" for cup in world.required_cups_in_order}
        | {f"{cup} - Bronze" for cup in world.required_cups_in_order}
        | {f"{track} - 1st Place" for track in world.required_race_tracks}
        | {f"{track} - 2nd Place" for track in world.required_race_tracks}
        | {f"{track} - 3rd Place" for track in world.required_race_tracks}
        | {f"{track} - Staff Ghost Beaten" for track in world.required_time_trials_in_order}
        | {f"{mission} - Clear" for mission in world.required_missions_in_order}
    )


def set_rules(world) -> None:
    player = world.player
    multiworld = world.multiworld

    # One bootstrap location per active category is unconditionally reachable; every
    # other location in that category needs its own individually-named unlock item (see
    # module docstring's fourth 2026-08-06 redesign note) - Cups, Time Trial, and
    # Missions all use the exact same pattern now, unconditionally (no capacity fallback
    # needed - see items.py's module docstring). A track's Grand Prix placement
    # locations share their parent cup's own rule - the bootstrap cup's own tracks are
    # free too, every other cup's tracks need that same cup's own unlock item - since
    # required_race_tracks has always been derived purely from required_cups_in_order,
    # not a separately-gated category of its own.
    always_true = lambda state: True

    def individual_unlock_rule(entry: str, bootstrap: Optional[str]):
        if entry == bootstrap:
            return always_true
        return lambda state: state.has(entry, player)

    cup_rule_by_track = {}
    for cup in world.required_cups_in_order:
        rule = individual_unlock_rule(cup, world.cup_bootstrap)
        for suffix in ("Win", "Silver", "Bronze"):
            set_rule(multiworld.get_location(f"{cup} - {suffix}", player), rule)
        for track in TRACKS_BY_CUP[cup]:
            cup_rule_by_track[track] = rule

    for track in world.required_race_tracks:
        rule = cup_rule_by_track[track]
        for suffix in ("1st Place", "2nd Place", "3rd Place"):
            set_rule(multiworld.get_location(f"{track} - {suffix}", player), rule)

    for track in world.required_time_trials_in_order:
        rule = individual_unlock_rule(track, world.time_trial_bootstrap)
        set_rule(multiworld.get_location(f"{track} - Staff Ghost Beaten", player), rule)

    for mission in world.required_missions_in_order:
        rule = individual_unlock_rule(mission, world.mission_bootstrap)
        set_rule(multiworld.get_location(f"{mission} - Clear", player), rule)

    # NOTE: these are the LOGICAL/generation-time completion conditions (used by AP's own
    # solver, hints, spoiler playthrough, etc.) - per direct user direction (see module
    # docstring's fifth 2026-08-06 redesign note), completion is checked directly against
    # the REQUIRED locations' own reachability, NOT a received item count. Each leg here
    # is only added if that category actually has required content - the
    # choose_goal_required_* functions already return an empty list when a category isn't
    # part of the selected goal. This is deliberately NOT the same thing as the real-time
    # trigger that actually ends the player's game: that comes from client.py's
    # game_watcher (_check_goal_complete), which reads ctx.checked_locations directly
    # against each category's required win COUNT (the player can stop as soon as N of
    # them are done, in any order/subset of their choosing) - AP's own logic-state solver
    # has no way to represent that choice, so this errs toward requiring every required
    # location reachable (a true superset of the real requirement, never a false one).
    conditions = []
    for cup in world.required_cups_in_order:
        conditions.append(lambda state, name=f"{cup} - Win": state.can_reach_location(name, player))
    for track in world.required_time_trials_in_order:
        conditions.append(lambda state, name=f"{track} - Staff Ghost Beaten": state.can_reach_location(name, player))
    for mission in world.required_missions_in_order:
        conditions.append(lambda state, name=f"{mission} - Clear": state.can_reach_location(name, player))

    if conditions:
        multiworld.completion_condition[player] = lambda state: all(condition(state) for condition in conditions)
