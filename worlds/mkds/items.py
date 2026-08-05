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
from . import rom_addresses
from .locations import CUPS, TRACKS, MISSIONS

base_id = 0xADF000  # verified against 49/~90 bundled worlds, see note above - not exhaustive


class ItemData(NamedTuple):
    code: Optional[int]
    classification: ItemClassification


# --- Characters (Useful, not gating) -----------------------------------------------
# All 12 playable characters (rom_addresses.CHARACTER_ID_TO_NAME is the single source of
# truth - kept there since client.py already needs it for character_id -> name
# resolution, no reason to maintain a second hardcoded roster here that could drift).
# One random character is free per seed (position 0 of rules.choose_character_unlock_
# order - mirrors how cups/tracks/missions each have their own free position 0) - the
# other 11 each get their own directly-named item, same pattern as cups/tracks/missions
# below. Superseded design: this list used to hold only the 4 characters that had an
# individually-isolated unlock bit in the OLD incremental-write scheme (the other 8 were
# a fixed "always free" starter set) - that distinction no longer exists under trust-based
# enforcement (see client.py's module docstring), since NO character needs a real unlock
# bit anymore (the game is forced fully unlocked regardless) - "legitimate" is now purely
# about which items were received, symmetric across all 12.
CHARACTERS = list(rom_addresses.CHARACTER_ID_TO_NAME.values())

# --- Karts (Useful, not gating - mirrors Characters exactly) ------------------------
# All 36 real karts (3 per character x 12 characters - rom_addresses.KART_ID_TO_NAME is
# the single source of truth, wiki-cross-verified against the real mkds-re KartId enum,
# same pattern as CHARACTERS above). One random kart is free per seed (position 0 of
# rules.choose_kart_unlock_order - mirrors Characters' own free-by-name position 0
# exactly, checked client-side only, see client.py's _is_run_legitimate) - the other 35
# each get their own one-copy Useful item. Each kart item legitimizes exactly its own
# kart_id, for whichever character used it (mkds-re confirms no engine-level character/
# kart pairing restriction - see rom_addresses.py's CHARKARTCTX_OFFSET_KART_IDX note).
#
# Supersedes an earlier design that collapsed every character's standard-tier kart into
# one shared "Standard Kart" item and left the other 24 (2 per character) with no item
# at all - meaning 24 of 36 real karts could never legitimize a check no matter what, and
# "Randomize Karts: Yes all" (per Instructions.txt) was never actually delivered. That
# collapse existed to sidestep a UX problem from an earlier, since-abandoned design
# (patching the game to restrict which of several received karts is "active" - see
# NOTES.md) - moot under trust-based enforcement, since the game was never actually
# restricting kart SELECTION in the first place.
#
# CLASSIFICATION: useful, matching Instructions.txt directly (no deviation, unlike the
# "Standard Kart" design this replaced). A REAL, SHIPPED BUG was found and fixed getting
# here: an earlier version of THIS redesign made karts mandatory Progression items,
# access-rule-gated via state.has_any(KARTS, player) (mirroring cups/tracks/missions).
# That's fine when a category naturally provides multiple simultaneously-free locations
# to bootstrap into (cups do, via their 4 associated tracks sharing one access rule) -
# but for a THIN category (missions, time trials - exactly 1 location per required
# instance), it created a real, provable fill deadlock: two DIFFERENT mandatory items (a
# kart and the category's own position-1 item) both need the SAME single always-free
# bootstrap location to be placed at, which is mathematically unsatisfiable (whichever
# one doesn't fit ends up needing itself). This wasn't a new bug from expanding to 36
# karts either - the OLD single "Standard Kart" item had the exact same shape and would
# have hit the same deadlock for any missions_count/time_trials_count goal (count >= 2)
# combined with Randomize Karts, just never exercised by a test. Reclassifying Karts as
# Useful (this design) removes them from the access-rule graph entirely, eliminating the
# deadlock at its root - see test/__init__.py's dedicated regression test for the exact
# formerly-broken configuration.
KARTS = list(rom_addresses.KART_ID_TO_NAME.values())

# --- Cup / Time Trial / Mission unlock items (Progression) ----------------------------
# One item PER CUP, PER TRACK, and PER MISSION, named directly after what it unlocks -
# e.g. receiving "Special Cup" unlocks Special Cup. Missions follow this exact pattern
# too (added later than cups/tracks, same reasoning throughout this block applies
# unchanged - one item per required mission, position 0 free). Replaces an earlier design
# that used a single
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
# Cups, tracks, and missions (CUPS/TRACKS/MISSIONS) live in locations.py - that's the
# authoritative source, not duplicated here. Every one of the 8 cups, 32 tracks, and 63
# missions gets a static item table entry (needed regardless of which ones end up
# goal-required in a given seed, same as location_table covers every possible location up
# front) - create_items() only actually creates/places the ones a specific seed's
# required_cups_in_order/required_time_trials_in_order/required_missions_in_order call
# for (skipping position 0 in each, per above).
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

    for name in MISSIONS:
        table[name] = ItemData(next_id, ItemClassification.progression)
        next_id += 1

    table[FILLER_ITEM_NAME] = ItemData(next_id, ItemClassification.filler)
    next_id += 1

    return table


item_table = build_item_table()
