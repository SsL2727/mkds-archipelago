# __init__.py
#
# World definition for Mario Kart DS. See Instructions.txt (project root) for the design
# spec and NOTES.md for implementation-side technical findings this code is built on.

from typing import Optional

from BaseClasses import Item, Tutorial
from worlds.AutoWorld import WebWorld, World

from .client import MKDSClient  # noqa: F401  (imported for its registration side effect - see client.py)
from .items import item_table, FILLER_ITEM_NAME
from .locations import location_table
from .options import MKDSOptions
from .regions import create_regions
from .rules import decide_goal_requirements, set_rules


class MKDSWebWorld(WebWorld):
    theme = "grass"

    setup_en = Tutorial(
        "Multiworld Setup Guide",
        "A guide to playing Mario Kart DS with Archipelago",
        "English",
        "setup_en.md",
        "setup/en",
        ["EAGPB"],  # TODO: real author credit
    )

    tutorials = [setup_en]


class MKDSItem(Item):
    game: str = "Mario Kart DS"


class MKDSWorld(World):
    game = "Mario Kart DS"
    web = MKDSWebWorld()

    options_dataclass = MKDSOptions
    options: MKDSOptions  # type: ignore

    item_name_to_id = {name: data.code for name, data in item_table.items()}
    location_name_to_id = {name: data.code for name, data in location_table.items()}

    required_locations: set  # populated by decide_goal_requirements() in generate_early
    required_cups_in_order: list  # ditto - ALL 8 cups or [], see rules.py's module docstring
    required_cup_win_count: int  # ditto - how many Cup Trophy needed to satisfy the goal
    required_time_trials_in_order: list  # ditto - ALL 32 tracks or []
    required_time_trial_win_count: int  # ditto
    required_missions_in_order: list  # ditto - ALL 63 missions or []
    required_mission_win_count: int  # ditto
    required_race_tracks: set  # ditto
    character_unlock_order: list  # ditto
    kart_unlock_order: list  # ditto
    cup_bootstrap: Optional[str]  # ditto - the one cup free with zero items this seed, or None
    time_trial_bootstrap: Optional[str]  # ditto - the one Time Trial track free with zero items, or None
    mission_bootstrap: Optional[str]  # ditto - the one mission free with zero items, or None

    def generate_early(self) -> None:
        self.options.validate()
        decide_goal_requirements(self)  # must run before create_items()/set_rules()

    def get_filler_item_name(self) -> str:
        return FILLER_ITEM_NAME

    def create_regions(self) -> None:
        create_regions(self)

    def create_item(self, name: str) -> MKDSItem:
        data = item_table[name]
        return MKDSItem(name, data.classification, data.code, self.player)

    def create_items(self) -> None:
        # REDESIGNED 2026-08-06 (see rules.py's/items.py's module docstrings for the full
        # reasoning, including a real design flaw found and fixed along the way): every
        # cup/track/mission is a real, checkable location, gated only on its own
        # individually-named unlock item (items.py's CUP_UNLOCK_NAMES/TRACK_UNLOCK_NAMES/
        # MISSION_UNLOCK_NAMES - literally the cup/track/mission's own name) - one
        # bootstrap entry per active category is free, every other entry needs its own
        # item, unconditionally (no capacity fallback needed for any of the three
        # categories - see items.py's module docstring for the math proving this always
        # fits). There is deliberately NO separate fungible "Trophy" item anymore -
        # completion is checked directly against location reachability (rules.py's
        # completion_condition) and real-time checked_locations (client.py's
        # _check_goal_complete), not a received item count, so there's nothing here
        # sized to a win target - every location this seed creates that isn't a
        # top-tier unlock gate (cup Silver/Bronze, race placements) gets ordinary filler
        # via the padding loop below, same as it always has.
        progression_pool: list[MKDSItem] = []
        progression_pool.extend(
            self.create_item(cup)
            for cup in self.required_cups_in_order
            if cup != self.cup_bootstrap
        )
        progression_pool.extend(
            self.create_item(track)
            for track in self.required_time_trials_in_order
            if track != self.time_trial_bootstrap
        )
        progression_pool.extend(
            self.create_item(mission)
            for mission in self.required_missions_in_order
            if mission != self.mission_bootstrap
        )

        location_count = len(self.required_locations)
        # Safety net, not expected to ever fire: each category's own individual-unlock
        # demand is (M - 1), always less than its own M real locations (see items.py's
        # module docstring) - fail loudly here rather than let the ordinary
        # filler-padding loop below silently under-pad and defer to a much more cryptic
        # Fill.FillError deep in generation, in case that invariant ever drifts.
        assert len(progression_pool) <= location_count, (
            f"MKDS create_items: {len(progression_pool)} mandatory items for only "
            f"{location_count} locations - this should never happen, see module docstring"
        )

        # Characters and Karts, if their Randomize options are on - one random one of
        # each is likewise free per seed (character_unlock_order[0]/kart_unlock_order[0],
        # checked by name only in client.py - mirrors the cup/track/mission pattern above
        # but WITHOUT an item, since neither gates any location's reachability - see
        # rules.py's module docstring), the rest as one-copy-each Useful items. Both
        # share ONE combined bonus pool/capacity computation (rather than two separate
        # ones) so trimming - if the pool would otherwise overflow - draws fairly from
        # both categories instead of always favoring whichever is computed first.
        #
        # Real bug found and fixed while building this: an earlier version made Karts
        # mandatory Progression items (rules.py access-rule-gated via
        # state.has_any(KARTS, player), mirroring cups/tracks/missions) sized to fit
        # available capacity. That avoided pool OVERFLOW but not a deeper problem - for a
        # THIN category (missions/time trials, exactly 1 location per required instance),
        # it created a real, provable fill DEADLOCK: two different mandatory items (a
        # kart and the category's own next item) both needing the SAME single always-free
        # bootstrap location is mathematically unsatisfiable, regardless of fill order.
        # Reclassifying Karts as Useful (items.py) and giving one a free identity by name
        # (rules.choose_kart_unlock_order, exactly like Characters) removes them from the
        # access-rule graph entirely, which removes the deadlock at its root - see
        # test/__init__.py's dedicated regression test for the exact formerly-broken
        # configuration.
        bonus_names: list[str] = []
        if self.options.randomize_characters:
            bonus_names.extend(self.character_unlock_order[1:])
        if self.options.randomize_karts:
            bonus_names.extend(self.kart_unlock_order[1:])

        bonus_capacity = max(0, location_count - len(progression_pool))
        if len(bonus_names) > bonus_capacity:
            # Not enough room for every Character/Kart - keep a random subset rather than
            # always dropping the same ones (e.g. always the last N alphabetically, or
            # always favoring one category over the other).
            bonus_names = self.random.sample(bonus_names, bonus_capacity)
        bonus_pool = [self.create_item(name) for name in bonus_names]

        pool = progression_pool + bonus_pool
        while len(pool) < location_count:
            pool.append(self.create_item(FILLER_ITEM_NAME))

        self.multiworld.itempool += pool

    def set_rules(self) -> None:
        set_rules(self)

    def fill_slot_data(self) -> dict:
        # REDESIGNED 2026-08-06 (see rules.py's module docstring): cups/tracks/missions
        # are no longer sequentially item-gated, so client.py doesn't need an "unlock
        # order" for them anymore - required_cups_in_order/required_time_trials_in_order/
        # required_missions_in_order now just tell it WHICH cups/tracks/missions are part
        # of the goal at all (empty means that category isn't in play this seed), and the
        # matching *_win_count tells it how many of that category's REQUIRED locations
        # need to show up in the live server's checked_locations before calling
        # CLIENT_GOAL - see client.py's _check_goal_complete (rewritten alongside this
        # redesign to check real checked locations directly, not a received item count -
        # see items.py's module docstring for why the item-count approach was removed).
        #
        # character_unlock_order/kart_unlock_order: unaffected by today's redesign, still
        # the per-seed randomized order client.py's _is_run_legitimate needs to know which
        # one ([0]) is this seed's free starting character/kart. Empty when the
        # corresponding Randomize option is off, which client.py treats as "this category
        # isn't part of the economy at all" - same on/off-switch pattern as before.
        #
        # cup_bootstrap/time_trial_bootstrap/mission_bootstrap: which single cup/track/
        # mission is freely reachable with zero items this seed (None if that category
        # isn't active at all). Not currently read by client.py (check-sending has never
        # depended on AP-logic reachability, only character/kart legitimacy - see
        # client.py's module docstring) - exposed for the same reason
        # character_unlock_order/kart_unlock_order are: so a consumer (e.g. PopTracker)
        # doesn't have to re-derive a generation-time random choice from scratch.
        return {
            "required_cups_in_order": self.required_cups_in_order,
            "required_cup_win_count": self.required_cup_win_count,
            "required_time_trials_in_order": self.required_time_trials_in_order,
            "required_time_trial_win_count": self.required_time_trial_win_count,
            "required_missions_in_order": self.required_missions_in_order,
            "required_mission_win_count": self.required_mission_win_count,
            "required_race_tracks": sorted(self.required_race_tracks),
            "character_unlock_order": self.character_unlock_order,
            "kart_unlock_order": self.kart_unlock_order,
            "cup_bootstrap": self.cup_bootstrap,
            "time_trial_bootstrap": self.time_trial_bootstrap,
            "mission_bootstrap": self.mission_bootstrap,
        }
