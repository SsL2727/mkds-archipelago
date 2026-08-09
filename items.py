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

# --- Individual Cup/Time Trial/Mission unlock items (Progression, one per entry) -------
# REDESIGNED 2026-08-06, per user direction: "all items from categories that include at
# least one location must be accessible" - every cup/track/mission a category could ever
# grant a check for is now ALWAYS a real AP location whenever that category is part of
# the goal at all (not just a pre-chosen subset sized to the configured count), and the
# player picks freely which ones to actually go complete.
#
# REDESIGNED AGAIN 2026-08-06, per user direction: "the player should only start with
# either 1 cup, time trial, or mission" - each active category starts with exactly ONE
# randomly-chosen bootstrap location freely reachable (see rules.py's
# choose_category_bootstrap), same "random position, no item needed" idea
# choose_character_unlock_order/choose_kart_unlock_order already use, just applied per
# category instead of per character/kart.
#
# REDESIGNED A THIRD TIME 2026-08-06: "don't unlock everything at once through one item.
# Each time trial and mission should be unlocked individually."
#
# REDESIGNED A FOURTH TIME 2026-08-06: "Cups should also be unlocked individually along
# with drivers and karts. Everything should be unlocked individually." Every cup/track/
# mission gets its own directly-named Progression item, mirroring Characters/Karts' own
# "one free by name, the rest individually named" pattern exactly (and the OLDEST
# pre-2026-08-06 design, before any of today's several redesigns) - receiving
# CUP_NAME/TRACK_NAME/MISSION_NAME makes exactly that one cup/track/mission's own
# locations reachable, nothing else.
#
# REDESIGNED A FIFTH TIME 2026-08-06, per direct user direction, removing an earlier
# mistake: "I do not want any item that counts towards the goal. The only thing that
# counts towards the goal is complete the cup, time trial, or mission." An earlier
# version of this file also had a separate fungible "Trophy" item per category (Cup
# Trophy/Staff Ghost Trophy/Mission Trophy), awarded on top of the real check, purely to
# give rules.py's completion_condition something item-shaped to count. That was a real
# design flaw the user correctly called out: because Trophy copies were ordinary shuffled
# Progression items, the fill algorithm could place any given copy at ANY reachable
# location - not necessarily the specific cup/track/mission it was "for" - so a player
# could in principle satisfy the goal by receiving N Trophy copies from unrelated checks
# (or even another player's world) without ever actually completing that many
# cups/tracks/missions themselves. Removed entirely - see rules.py's completion_condition
# for what replaced it (checking whether the REQUIRED locations themselves are
# reachable/completed, not counting a received item).
#
# Capacity note: without a Trophy item competing for room, every category's individual-
# unlock demand is just (M - 1) - always less than its own M real locations - so ALL
# THREE categories (Cups, Time Trial, Missions) now unconditionally use individual
# unlocking with no fallback needed at all (mirroring Characters/Karts exactly) - the
# earlier "Time Trial Key"/"Mission Key" shared-Key fallback and its whole capacity-
# solving mechanism (rules.decide_unlock_modes) existed only to make room for Trophy
# copies alongside individual unlock items, and is gone now that there's nothing left to
# make room for.
CUP_UNLOCK_NAMES = list(CUPS)
TRACK_UNLOCK_NAMES = list(TRACKS)
MISSION_UNLOCK_NAMES = list(MISSIONS)

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

    for name in CUP_UNLOCK_NAMES:
        table[name] = ItemData(next_id, ItemClassification.progression)
        next_id += 1

    for name in TRACK_UNLOCK_NAMES:
        table[name] = ItemData(next_id, ItemClassification.progression)
        next_id += 1

    for name in MISSION_UNLOCK_NAMES:
        table[name] = ItemData(next_id, ItemClassification.progression)
        next_id += 1

    table[FILLER_ITEM_NAME] = ItemData(next_id, ItemClassification.filler)
    next_id += 1

    return table


item_table = build_item_table()
