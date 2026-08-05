# __init__.py
#
# World definition for Mario Kart DS. See Instructions.txt (project root) for the design
# spec and NOTES.md for implementation-side technical findings this code is built on.

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
    required_cups_in_order: list  # ditto
    required_time_trials_in_order: list  # ditto
    required_missions_in_order: list  # ditto
    required_race_tracks: set  # ditto
    character_unlock_order: list  # ditto
    kart_unlock_order: list  # ditto

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
        # Real (non-filler) item pool per Instructions.txt, since redesigned around
        # trust-based check enforcement (see rules.py's module docstring/NOTES.md): one
        # item PER goal-required cup/track/mission, named directly after it (e.g.
        # receiving "Special Cup" unlocks Special Cup) - see items.py's header comment
        # for why this replaced an earlier generic counted "Progressive Cup" design. The
        # FIRST required cup, FIRST required track, and FIRST required mission each need
        # no item at all (rules.py gives them an unconditional access rule - they're the
        # bootstrap entry point into their respective chains, matching "you always have
        # somewhere to start"), so `[1:]` below is intentional, not an off-by-one bug.
        #
        # Cup/track/mission items are PROGRESSION and unconditionally mandatory - every
        # one is required for logical completion (rules.py's access rules and
        # completion_condition depend on having received them all) - this is the real
        # floor `location_count` below must accommodate.
        progression_pool: list[MKDSItem] = []
        progression_pool.extend(self.create_item(cup) for cup in self.required_cups_in_order[1:])
        progression_pool.extend(self.create_item(track) for track in self.required_time_trials_in_order[1:])
        progression_pool.extend(self.create_item(mission) for mission in self.required_missions_in_order[1:])

        location_count = len(self.required_locations)

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
        # client.py needs the generation-time unlock order itself (decided per-seed in
        # generate_early - see rules.choose_goal_required_cups/_time_trials/_missions)
        # since each cup/track/mission's unlock item is named directly after it, and
        # which cups/tracks/missions aren't part of the AP economy at all (goal-scoping -
        # those should be left to vanilla progression, not touched by the client).
        #
        # character_unlock_order/kart_unlock_order: same idea, but for Characters/Karts
        # specifically - neither is goal-scoped (see rules.choose_character_unlock_order/
        # choose_kart_unlock_order), just the per-seed randomized order client.py's
        # _is_run_legitimate needs to know which one ([0]) is this seed's free starting
        # character/kart. Empty when the corresponding Randomize option is off, which
        # client.py treats as "this category isn't part of the economy at all" - same
        # on/off-switch pattern for both.
        return {
            "required_cups_in_order": self.required_cups_in_order,
            "required_time_trials_in_order": self.required_time_trials_in_order,
            "required_missions_in_order": self.required_missions_in_order,
            "required_race_tracks": sorted(self.required_race_tracks),
            "character_unlock_order": self.character_unlock_order,
            "kart_unlock_order": self.kart_unlock_order,
        }
