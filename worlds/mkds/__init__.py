# __init__.py
#
# World definition for Mario Kart DS. See Instructions.txt (project root) for the design
# spec and NOTES.md for implementation-side technical findings this code is built on.

from BaseClasses import Item, Tutorial
from worlds.AutoWorld import WebWorld, World

from .client import MKDSClient  # noqa: F401  (imported for its registration side effect - see client.py)
from .items import item_table, CHARACTERS, KARTS, FILLER_ITEM_NAME
from .locations import location_table
from .options import MKDSOptions, RandomizeKarts
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
    required_missions: list  # ditto
    required_race_tracks: set  # ditto

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
        # Real (non-filler) item pool per Instructions.txt: Characters/Karts (if their
        # Randomize options are on) as one-copy-each Useful items, plus one item PER
        # goal-required cup/track, named directly after it (e.g. receiving "Special Cup"
        # unlocks Special Cup) - see items.py's header comment for why this replaced an
        # earlier generic counted "Progressive Cup" design (real playtesting, 2026-08-04:
        # players had no way to tell which cup a received item corresponded to). The
        # FIRST required cup and FIRST required track need no item at all (rules.py gives
        # them an unconditional access rule - they're the bootstrap entry point into
        # their respective chains, matching "you always have somewhere to start"), so
        # `[1:]` is intentional, not an off-by-one bug.
        #
        # Missions are locations, not items, so they don't belong in this pool at all
        # (see items.py header comment, and rules.py's module docstring) - not an
        # oversight.
        #
        # Cup/track unlock items are PROGRESSION items - every one is required for
        # logical completion (rules.py's access rules and completion_condition depend on
        # having received them), so they always go in whole. Characters/Karts are only
        # "Useful" (see items.py) - not required for completion - so if the pool would
        # overflow the goal-required location count, THESE are what gets trimmed, not the
        # progression items. Instructions.txt's own assumption was "pool overflow is not
        # expected to occur", but real generation testing (2026-08-04) proved it does for
        # smaller goals combined with both Randomize Characters and Randomize Karts on
        # (e.g. combination goal, required_cup_count=3: only ~31 locations exist, but
        # Characters(4)+Karts(36)=40 alone already exceeds that) - this handles it rather
        # than leaving generation to hard-fail on an unplaceable pool.
        progression_pool: list[MKDSItem] = []
        progression_pool.extend(self.create_item(cup) for cup in self.required_cups_in_order[1:])
        progression_pool.extend(self.create_item(track) for track in self.required_time_trials_in_order[1:])

        bonus_names: list[str] = []
        if self.options.randomize_characters:
            bonus_names.extend(CHARACTERS)
        if self.options.randomize_karts.value != RandomizeKarts.option_off:
            bonus_names.extend(KARTS)

        location_count = len(self.required_locations)
        bonus_capacity = max(0, location_count - len(progression_pool))
        if len(bonus_names) > bonus_capacity:
            # Not enough room for every Character/Kart - keep a random subset rather than
            # always dropping the same ones (e.g. always the last N alphabetically).
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
        # generate_early - see rules.choose_goal_required_cups/_time_trials) since each
        # cup/track's unlock item is named directly after it, and which cups/tracks/
        # missions aren't part of the AP economy at all (goal-scoping - those should be
        # left to vanilla progression, not touched by the client).
        return {
            "required_cups_in_order": self.required_cups_in_order,
            "required_time_trials_in_order": self.required_time_trials_in_order,
            "required_missions": self.required_missions,
            "required_race_tracks": sorted(self.required_race_tracks),
        }
