from test.bases import WorldTestBase

from ..locations import TRACKS_BY_CUP


class MKDSTestBase(WorldTestBase):
    game = "Mario Kart DS"


# REDESIGNED 2026-08-06 (see rules.py's module docstring, first pass): Cups/Time
# Trials/Missions are no longer sequentially item-gated subsets - every cup/track/mission
# in an active category is a real location.
#
# REDESIGNED AGAIN 2026-08-06 (second/third/fourth passes): each active category starts
# with exactly ONE randomly-chosen bootstrap location reachable with zero items - every
# OTHER cup/track/mission needs its own individually-named unlock item (mirroring
# Characters/Karts' own "one free by name, the rest individually named" pattern),
# unconditionally, no capacity fallback needed (see items.py's module docstring).
#
# REDESIGNED A FIFTH TIME 2026-08-06, removing a real design flaw: there is no more
# fungible "Trophy" item at all. rules.py's completion_condition checks REQUIRED
# locations' own reachability directly - and since required_cups_in_order/
# required_time_trials_in_order/required_missions_in_order are always the FULL category
# (all 8 cups/32 tracks/63 missions) whenever that category is active AT ALL (never a
# subset sized to the configured count - see choose_goal_required_cups/_time_trials/
# _missions), completion_condition ends up requiring the ENTIRE category reachable
# regardless of what required_cup_count/required_time_trial_count/required_mission_count
# was configured to. This is intentional (see rules.py's module docstring): AP's
# logic-state solver has no way to represent "the player will stop after N of their own
# choosing" - only client.py's real-time _check_goal_complete enforces the actual N
# threshold, by reading ctx.checked_locations directly. So below, assertBeatable(True)
# always requires collecting EVERY non-bootstrap entry's own unlock item in a category,
# never just a "count"-sized subset - that's the real, if slightly surprising,
# consequence of moving off item-counted completion.


class TestCupsAll(MKDSTestBase):
    options = {
        "goal": "cups_all",
        "required_time_trial_count": 0,
        "required_mission_count": 0,
    }

    def test_goal(self) -> None:
        self.assertBeatable(False)
        cup_names = [c for c in self.world.required_cups_in_order if c != self.world.cup_bootstrap]
        self.assertEqual(len(cup_names), 7)  # 8 cups total, minus the free bootstrap one
        cups = self.get_items_by_name(cup_names)
        self.collect(cups[:-1])
        self.assertBeatable(False)
        self.collect(cups[-1:])
        self.assertBeatable(True)


class TestCupsCount(MKDSTestBase):
    """required_cup_count only affects client.py's real-time goal check (module
    docstring above) - at the generation-time LOGIC level, completion_condition still
    requires the full 8-cup category reachable, same as TestCupsAll, regardless of this
    "count" being only 3."""
    options = {
        "goal": "cups_count",
        "required_cup_count": 3,
        "required_time_trial_count": 0,
        "required_mission_count": 0,
    }

    def test_goal(self) -> None:
        self.assertBeatable(False)
        cup_names = [c for c in self.world.required_cups_in_order if c != self.world.cup_bootstrap]
        self.assertEqual(len(cup_names), 7)  # still all 8 cups active, not just 3
        cups = self.get_items_by_name(cup_names)
        self.collect(cups[:-1])
        self.assertBeatable(False)
        self.collect(cups[-1:])
        self.assertBeatable(True)


class TestMissionModeComplete(MKDSTestBase):
    options = {
        "goal": "mission_mode_complete",
        "randomize_mission_mode": True,
        "required_time_trial_count": 0,  # avoid the "count set but category off" OptionError
    }

    def test_goal(self) -> None:
        self.assertBeatable(False)
        mission_names = [m for m in self.world.required_missions_in_order if m != self.world.mission_bootstrap]
        self.assertEqual(len(mission_names), 62)  # 63 missions total, minus the free bootstrap one
        missions = self.get_items_by_name(mission_names)
        self.collect(missions[:-1])
        self.assertBeatable(False)
        self.collect(missions[-1:])
        self.assertBeatable(True)


class TestMissionsCount(MKDSTestBase):
    options = {
        "goal": "missions_count",
        "randomize_mission_mode": True,
        "required_mission_count": 10,
        "required_time_trial_count": 0,
    }

    def test_goal(self) -> None:
        self.assertBeatable(False)
        mission_names = [m for m in self.world.required_missions_in_order if m != self.world.mission_bootstrap]
        self.assertEqual(len(mission_names), 62)  # still all 63 missions active, not just 10
        missions = self.get_items_by_name(mission_names)
        self.collect(missions[:-1])
        self.assertBeatable(False)
        self.collect(missions[-1:])
        self.assertBeatable(True)


class TestTimeTrialsAll(MKDSTestBase):
    options = {
        "goal": "time_trials_all",
        "randomize_time_trial": True,
        "required_mission_count": 0,  # avoid the "count set but category off" OptionError
    }

    def test_goal(self) -> None:
        self.assertBeatable(False)
        track_names = [t for t in self.world.required_time_trials_in_order if t != self.world.time_trial_bootstrap]
        self.assertEqual(len(track_names), 31)  # 32 tracks total, minus the free bootstrap one
        staff_ghosts = self.get_items_by_name(track_names)
        self.collect(staff_ghosts[:-1])
        self.assertBeatable(False)
        self.collect(staff_ghosts[-1:])
        self.assertBeatable(True)


class TestTimeTrialsCount(MKDSTestBase):
    options = {
        "goal": "time_trials_count",
        "randomize_time_trial": True,
        "required_time_trial_count": 5,
        "required_mission_count": 0,
    }

    def test_goal(self) -> None:
        self.assertBeatable(False)
        track_names = [t for t in self.world.required_time_trials_in_order if t != self.world.time_trial_bootstrap]
        self.assertEqual(len(track_names), 31)  # still all 32 tracks active, not just 5
        staff_ghosts = self.get_items_by_name(track_names)
        self.collect(staff_ghosts[:-1])
        self.assertBeatable(False)
        self.collect(staff_ghosts[-1:])
        self.assertBeatable(True)


class TestCupIndividualUnlock(MKDSTestBase):
    """Direct reachability test: with zero items, only the ONE randomly-chosen bootstrap
    cup (and its own 4 tracks' Grand Prix placement locations) should be reachable -
    every OTHER cup (and its own 4 tracks) needs THAT SPECIFIC cup's own item, not some
    other cup's."""
    options = {
        "goal": "cups_count",
        "required_cup_count": 3,
        "required_time_trial_count": 0,
        "required_mission_count": 0,
    }

    def test_individual_unlock(self) -> None:
        bootstrap = self.world.cup_bootstrap
        self.assertIsNotNone(bootstrap)
        self.assertIn(bootstrap, self.world.required_cups_in_order)

        for suffix in ("Win", "Silver", "Bronze"):
            self.assertTrue(self.can_reach_location(f"{bootstrap} - {suffix}"))
        for track in TRACKS_BY_CUP[bootstrap]:
            for suffix in ("1st Place", "2nd Place", "3rd Place"):
                self.assertTrue(self.can_reach_location(f"{track} - {suffix}"))

        other_cups = [cup for cup in self.world.required_cups_in_order if cup != bootstrap]
        self.assertEqual(len(other_cups), 7)
        cup_a, cup_b = other_cups[0], other_cups[1]
        track_a = TRACKS_BY_CUP[cup_a][0]
        self.assertFalse(self.can_reach_location(f"{cup_a} - Win"))
        self.assertFalse(self.can_reach_location(f"{track_a} - 1st Place"))

        # Some OTHER cup's own item must NOT unlock cup_a - proves this is genuinely
        # per-cup, not a shared gate in disguise.
        self.collect(self.get_items_by_name(cup_b))
        self.assertFalse(self.can_reach_location(f"{cup_a} - Win"))

        self.collect(self.get_items_by_name(cup_a))
        for suffix in ("Win", "Silver", "Bronze"):
            self.assertTrue(self.can_reach_location(f"{cup_a} - {suffix}"))
        for track in TRACKS_BY_CUP[cup_a]:
            for suffix in ("1st Place", "2nd Place", "3rd Place"):
                self.assertTrue(self.can_reach_location(f"{track} - {suffix}"))


class TestTimeTrialIndividualUnlock(MKDSTestBase):
    """Same pattern as TestCupIndividualUnlock, for Time Trial."""
    options = {
        "goal": "time_trials_count",
        "randomize_time_trial": True,
        "required_time_trial_count": 5,
        "required_mission_count": 0,
    }

    def test_individual_unlock(self) -> None:
        bootstrap = self.world.time_trial_bootstrap
        self.assertIsNotNone(bootstrap)
        self.assertTrue(self.can_reach_location(f"{bootstrap} - Staff Ghost Beaten"))

        other_tracks = [t for t in self.world.required_time_trials_in_order if t != bootstrap]
        self.assertEqual(len(other_tracks), 31)
        track_a, track_b = other_tracks[0], other_tracks[1]
        self.assertFalse(self.can_reach_location(f"{track_a} - Staff Ghost Beaten"))

        self.collect(self.get_items_by_name(track_b))
        self.assertFalse(self.can_reach_location(f"{track_a} - Staff Ghost Beaten"))

        self.collect(self.get_items_by_name(track_a))
        self.assertTrue(self.can_reach_location(f"{track_a} - Staff Ghost Beaten"))


class TestMissionIndividualUnlock(MKDSTestBase):
    """Same pattern as TestCupIndividualUnlock, for Missions."""
    options = {
        "goal": "missions_count",
        "randomize_mission_mode": True,
        "required_mission_count": 10,
        "required_time_trial_count": 0,
    }

    def test_individual_unlock(self) -> None:
        bootstrap = self.world.mission_bootstrap
        self.assertIsNotNone(bootstrap)
        self.assertTrue(self.can_reach_location(f"{bootstrap} - Clear"))

        other_missions = [m for m in self.world.required_missions_in_order if m != bootstrap]
        self.assertEqual(len(other_missions), 62)
        mission_a, mission_b = other_missions[0], other_missions[1]
        self.assertFalse(self.can_reach_location(f"{mission_a} - Clear"))

        self.collect(self.get_items_by_name(mission_b))
        self.assertFalse(self.can_reach_location(f"{mission_a} - Clear"))

        self.collect(self.get_items_by_name(mission_a))
        self.assertTrue(self.can_reach_location(f"{mission_a} - Clear"))


class TestKartUnlockOrder(MKDSTestBase):
    """Karts don't gate any location's reachability (Useful, not Progression - see
    items.py), so this can't be verified via assertBeatable the way cups/tracks/missions
    are above - same limitation TestCharacterUnlockOrder already documents. Instead
    verifies create_items() actually produces the right number of non-free kart items
    (kart_unlock_order[1:] - see __init__.create_items) - a pool-content assertion, not
    a reachability one. cups_all makes all 8 cups (24 locations - Win/Silver/Bronze) and
    all 32 of their tracks (96 locations - 1st/2nd/3rd Place) active, 120 locations total,
    against only 7 mandatory items (one individual unlock item per non-bootstrap cup -
    there's no separate Trophy item anymore, see items.py's module docstring) - 113 bonus
    capacity, comfortably more than the 35 non-free karts, so this config doesn't
    exercise create_items()'s bonus-pool trimming (that's covered by
    TestKartsWithThinCategoryTrimming below instead, which stays thin regardless)."""
    options = {
        "goal": "cups_all",
        "randomize_karts": True,
        "required_time_trial_count": 0,
        "required_mission_count": 0,
    }

    def test_kart_item_count(self) -> None:
        kart_names = self.world.kart_unlock_order[1:]
        self.assertEqual(len(kart_names), 35)  # 36 karts total, minus the free first one
        karts = self.get_items_by_name(kart_names)
        self.assertEqual(len(karts), 35)  # 120 locations - 7 mandatory cup items = 113 capacity, no trimming needed


class TestKartsWithThinCategoryTrimming(MKDSTestBase):
    """Regression test for a real, provable fill deadlock found while expanding karts
    from a single "Standard Kart" item to all 36 real karts (predates every 2026-08-06
    cups/tracks/missions redesign - see items.py's Karts section for the full account).
    That deadlock class can't recur - Karts were reclassified Useful specifically to
    remove them from the access-rule graph entirely.

    What this test covers today: mission_mode_complete makes all 63 missions active,
    each needing its own individual unlock item except the one free bootstrap - 62
    mandatory items against 63 real mission locations, leaving exactly 1 slot of bonus
    capacity (no separate Trophy item competing for room anymore - see items.py's module
    docstring) for 46 combined Character/Kart candidates (11 non-free characters + 35
    non-free karts). Confirms create_items()'s trimming (self.random.sample(bonus_names,
    1)) handles this heavily-oversubscribed case gracefully rather than crashing."""
    options = {
        "goal": "mission_mode_complete",
        "randomize_mission_mode": True,
        "required_time_trial_count": 0,
        "randomize_karts": True,
        "randomize_characters": True,
    }

    def test_goal(self) -> None:
        bootstrap = self.world.mission_bootstrap
        self.assertIsNotNone(bootstrap)
        self.assertTrue(self.can_reach_location(f"{bootstrap} - Clear"))

        self.assertBeatable(False)
        mission_names = [m for m in self.world.required_missions_in_order if m != bootstrap]
        self.assertEqual(len(mission_names), 62)
        missions = self.get_items_by_name(mission_names)
        self.collect(missions[:-1])
        self.assertBeatable(False)
        self.collect(missions[-1:])
        self.assertBeatable(True)  # no kart or character item involved

        bonus_names = self.world.character_unlock_order[1:] + self.world.kart_unlock_order[1:]
        self.assertEqual(len(bonus_names), 46)  # 11 non-free characters + 35 non-free karts
        bonus_items = self.get_items_by_name(bonus_names)
        self.assertEqual(len(bonus_items), 1)  # 63 locations - 62 mandatory mission items = 1 slot


class TestCombination(MKDSTestBase):
    """Cups, Time Trials, and Missions are all part of the goal here - completion needs
    every non-bootstrap entry's own unlock item across ALL THREE categories (not just a
    "count"-sized subset of each - see module docstring)."""
    options = {
        "goal": "combination",
        "randomize_time_trial": True,
        "randomize_mission_mode": True,
        "required_cup_count": 3,
        "required_time_trial_count": 4,
        "required_mission_count": 6,
    }

    def test_goal(self) -> None:
        self.assertBeatable(False)
        cup_names = [c for c in self.world.required_cups_in_order if c != self.world.cup_bootstrap]
        track_names = [t for t in self.world.required_time_trials_in_order if t != self.world.time_trial_bootstrap]
        mission_names = [m for m in self.world.required_missions_in_order if m != self.world.mission_bootstrap]
        self.assertEqual(len(cup_names), 7)
        self.assertEqual(len(track_names), 31)
        self.assertEqual(len(mission_names), 62)

        self.collect(self.get_items_by_name(cup_names))
        self.collect(self.get_items_by_name(track_names))
        self.assertBeatable(False)  # cups + time trials alone aren't enough - missions still missing
        self.collect(self.get_items_by_name(mission_names))
        self.assertBeatable(True)


class TestCharacterUnlockOrder(MKDSTestBase):
    """Characters don't gate any location's reachability (Useful, not Progression - see
    items.py), so this can't be verified via assertBeatable the way cups/tracks/missions
    are above. Instead verifies create_items() actually produces one item per non-free
    character (character_unlock_order[1:] - see __init__.create_items) - a pool-content
    assertion, not a reachability one. Plenty of goal-required locations here (cups_all
    with no Time Trial/Mission Mode = 120, see TestKartUnlockOrder) relative to the 11
    character items, so none of them should hit create_items()'s bonus-pool trimming."""
    options = {
        "goal": "cups_all",
        "randomize_characters": True,
        "required_time_trial_count": 0,
        "required_mission_count": 0,
    }

    def test_character_item_count(self) -> None:
        character_names = self.world.character_unlock_order[1:]
        self.assertEqual(len(character_names), 11)  # 12 characters total, minus the free first one
        characters = self.get_items_by_name(character_names)
        self.assertEqual(len(characters), 11)
