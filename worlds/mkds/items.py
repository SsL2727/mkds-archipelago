# items.py
#
# Item table for the Mario Kart DS world. Characters and cup/track names are drawn from
# real MKDS content (cross-checked against the existing manual_mariokartds_xanderoni.apworld
# for a second source, plus general knowledge of the game). Anything not yet verified
# against the actual ROM/RAM is marked TODO below rather than asserted as fact.
#
# base_id: checked programmatically (2026-08-04) against every world that could actually
# load in this dev environment - imported AutoWorldRegister and diffed item_name_to_id
# values for all successfully-registered worlds against this range. 49 of the ~90 bundled
# worlds loaded (the rest failed on missing optional deps like bsdiff4/orjson/pyevermizer,
# unrelated to MKDS - see NOTES.md); zero exact ID collisions found among those 49.
# NOT exhaustive: doesn't cover the ~40 worlds that couldn't load here, and doesn't cover
# any community worlds a real player might have installed in their own custom_worlds
# folder (which this dev environment has no access to) - still worth a final check before
# shipping into a real multiworld with other players, but this is real, positive evidence
# rather than a pure placeholder guess now.

from typing import NamedTuple, Optional
from BaseClasses import ItemClassification
from .locations import CUPS, TRACKS

base_id = 0xADF000  # verified against 49/~90 bundled worlds, see note above - not exhaustive


class ItemData(NamedTuple):
    code: Optional[int]
    classification: ItemClassification


# --- Characters (Useful, not gating) -----------------------------------------------
# Only the 4 genuinely lockable characters - Mario/Luigi/Peach/Yoshi/Toad/Donkey Kong/
# Wario/Bowser are always available in vanilla MKDS with no unlock bit gating them at
# all (see rom_addresses.CHARACTER_UNLOCK_BITS), so an item for one of them would be
# received but do nothing (there's no bit for _apply_received_items to write) - purely
# wasted pool space, not something the AP economy can meaningfully represent. Previously
# this list held all 12 (full roster, cross-checked against manual_mariokartds_
# xanderoni's items.json) and fed straight into the item pool; real playtesting
# (2026-08-04) surfaced the same "content that can't actually be locked shouldn't be in
# the gated economy" issue already found for cups (see rules.py/NOTES.md) - fixed here
# by only including what can genuinely be unlocked.
CHARACTERS = ["Daisy", "Waluigi", "Dry Bones", "R.O.B."]

# --- Karts (Useful, not gating) -----------------------------------------------------
# Full 36-kart roster (3 per character), sourced from en.wikibooks.org/wiki/Mario_Kart_DS/Karts
# (2026-08-04) and cross-checked for internal consistency (an earlier, messier search
# result had a duplicated "Standard DS" name and gaps - not used).
#
# DEFAULT VS UNLOCKABLE: only Mario's is empirically confirmed via direct gameplay
# observation - his real starting karts are "B Dasher" and "Standard MR" (2 of his 3),
# with "Shooting Star" as the unlockable one. The Wikibooks source's own per-character
# "(default)" labels are NOT trusted for the other 11 characters - it explicitly says
# "at the beginning there are only two karts available per racer" (matching what we
# confirmed for Mario) "but doesn't explicitly distinguish which second kart is default
# versus unlockable" for the rest. Treat KART_DEFAULTS below as confirmed for Mario only;
# everyone else's split is a TODO.
#
# DESIGN NOTE: live testing suggests kart availability is not independently flag-gated
# in vanilla MKDS at all (unlocking characters cascaded to "all karts unlocked" rather
# than specific karts). Current plan is to randomize each character's *starting kart
# assignment* directly (a RAM/ROM patch) rather than rely on a native per-kart unlock
# flag - see rom_addresses.py's "still unmapped" section. This doesn't change the item
# list itself, just how receiving a "Kart" item eventually gets applied in-game.
KARTS_BY_CHARACTER = {
    "Mario": ["Standard MR", "B Dasher", "Shooting Star"],
    "Luigi": ["Standard LG", "Poltergust 4000", "Streamliner"],
    "Peach": ["Standard PC", "Royale", "Light Tripper"],
    "Yoshi": ["Standard YS", "Egg 1", "Cucumber"],
    "Toad": ["Standard TD", "Mushmellow", "4-Wheel Cradle"],
    "Donkey Kong": ["Standard DK", "Rambi Rider", "Wildlife"],
    "Wario": ["Standard WR", "Brute", "Dragonfly"],
    "Bowser": ["Standard BW", "Tyrant", "Hurricane"],
    "Dry Bones": ["Standard DB", "Banisher", "Dry Bomber"],
    "Daisy": ["Standard DS", "Power Flower", "Light Dancer"],
    "Waluigi": ["Standard WL", "Gold Mantis", "Zipper"],
    "R.O.B.": ["Standard RB", "ROB-BLS", "ROB-LGS"],
}
# Confirmed via direct gameplay (2026-08-04) - Mario only, see note above.
CONFIRMED_DEFAULT_KARTS = {"Mario": ["Standard MR", "B Dasher"]}

KARTS = [kart for karts in KARTS_BY_CHARACTER.values() for kart in karts]

# --- Cup / Time Trial unlock items (Progression) --------------------------------------
# One item PER CUP and PER TRACK, named directly after what it unlocks - e.g. receiving
# "Special Cup" unlocks Special Cup. Replaces an earlier design that used a single
# generically-named "Progressive Cup" item, counted (Nth copy unlocks the Nth required
# cup in generation-time order) - real playtesting (2026-08-04) found this confusing in
# practice ("You received: Progressive Cup!" doesn't say WHICH cup). Switching to
# directly-named items doesn't weaken the design in any real way: the old counted system
# never actually guaranteed the player would play through cups in strict left-to-right
# order either - since every copy was identical, the fill algorithm could freely place
# several/all of them within the very first required cup's own reachable locations,
# letting a player receive count=3 (say) without ever touching cups 1 or 2. Both designs
# provide the exact same structural guarantee: a solvable, well-defined access hierarchy
# where the FIRST required cup/track is free and every other one needs its own specific
# item to be found (rules.py gates that item's own PLACEMENT to somewhere already
# reachable, which is what actually creates progression, not receipt order of an
# otherwise-interchangeable counted item). See rules.py's set_rules for the access rules
# that pair with these names, and CHANGELOG-worthy behavior change: the FIRST required
# cup/track no longer gets an item created for it at all (nothing to unlock - it's free
# from the start), where the old design created one "spare" Progressive Cup copy per
# seed that wasn't strictly needed for access.
#
# Cups and tracks (CUPS/TRACKS) live in locations.py - that's the authoritative source,
# not duplicated here. Every one of the 8 cups and 32 tracks gets a static item table
# entry (needed regardless of which ones end up goal-required in a given seed, same as
# location_table covers every possible location up front) - create_items() only
# actually creates/places the ones a specific seed's required_cups_in_order/
# required_time_trials_in_order call for (skipping position 0 in each, per above).
FILLER_ITEM_NAME = "Green Flag"


def build_item_table() -> dict[str, ItemData]:
    table: dict[str, ItemData] = {}
    next_id = base_id

    for name in CHARACTERS:
        table[name] = ItemData(next_id, ItemClassification.useful)
        next_id += 1

    for name in KARTS:
        table[name] = ItemData(next_id, ItemClassification.useful)
        next_id += 1

    for name in CUPS:
        table[name] = ItemData(next_id, ItemClassification.progression)
        next_id += 1

    for name in TRACKS:
        table[name] = ItemData(next_id, ItemClassification.progression)
        next_id += 1

    table[FILLER_ITEM_NAME] = ItemData(next_id, ItemClassification.filler)
    next_id += 1

    return table


item_table = build_item_table()
