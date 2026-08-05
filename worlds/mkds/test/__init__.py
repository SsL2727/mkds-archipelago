from test.bases import WorldTestBase


class MKDSTestBase(WorldTestBase):
    game = "Mario Kart DS"


class TestCupsAll(MKDSTestBase):
    options = {
        "goal": "cups_all",
        "required_time_trial_count": 0,
        "required_mission_count": 0,
    }

    def test_goal(self) -> None:
        self.assertBeatable(False)
        # Position 0 (the first required cup, generation-time order) needs no item - see
        # rules.py's _sequence_access_rule - so only required_cups_in_order[1:] have one.
        cup_names = self.world.required_cups_in_order[1:]
        cups = self.get_items_by_name(cup_names)
        self.assertEqual(len(cups), 7)  # 8 required cups total, minus the free first one
        # Each cup's item independently gates only that cup (no positional chain - see
        # items.py's header comment) - completion needs ALL of them, any single one
        # withheld keeps its own cup (and therefore overall completion) unreachable.
        self.collect(cups[:-1])
        self.assertBeatable(False)
        self.collect(cups[-1:])
        self.assertBeatable(True)


class TestCupsCount(MKDSTestBase):
    options = {
        "goal": "cups_count",
        "required_cup_count": 3,
        "required_time_trial_count": 0,
        "required_mission_count": 0,
    }

    def test_goal(self) -> None:
        self.assertBeatable(False)
        cup_names = self.world.required_cups_in_order[1:]
        cups = self.get_items_by_name(cup_names)
        self.assertEqual(len(cups), 2)  # 3 required cups total, minus the free first one
        self.collect(cups[:1])
        self.assertBeatable(False)
        self.collect(cups[1:])
        self.assertBeatable(True)


class TestMissionModeComplete(MKDSTestBase):
    """Missions are now sequentially item-gated, mirroring TestCupsAll exactly - each
    required mission (after the first, free one) needs its own item (see rules.py module
    docstring). Randomize Karts stays off here - unlike cups/tracks/missions, Karts
    aren't access-rule-gated at all (Useful, not Progression - see items.py/
    TestKartUnlockOrder below), so there's nothing kart-related to layer on top here."""
    options = {
        "goal": "mission_mode_complete",
        "randomize_mission_mode": True,
        "required_time_trial_count": 0,  # avoid the "count set but category off" OptionError
    }

    def test_goal(self) -> None:
        self.assertBeatable(False)
        mission_names = self.world.required_missions_in_order[1:]
        missions = self.get_items_by_name(mission_names)
        self.assertEqual(len(missions), 62)  # 63 missions total, minus the free first one
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
        mission_names = self.world.required_missions_in_order[1:]
        missions = self.get_items_by_name(mission_names)
        self.assertEqual(len(missions), 9)  # 10 required missions total, minus the free first one
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
        track_names = self.world.required_time_trials_in_order[1:]
        staff_ghosts = self.get_items_by_name(track_names)
        self.assertEqual(len(staff_ghosts), 31)  # 32 required tracks, minus the free first one
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
        track_names = self.world.required_time_trials_in_order[1:]
        staff_ghosts = self.get_items_by_name(track_names)
        self.assertEqual(len(staff_ghosts), 4)  # 5 required tracks, minus the free first one
        self.collect(staff_ghosts[:-1])
        self.assertBeatable(False)
        self.collect(staff_ghosts[-1:])
        self.assertBeatable(True)


class TestKartUnlockOrder(MKDSTestBase):
    """Karts don't gate any location's reachability (Useful, not Progression - see
    items.py), so this can't be verified via assertBeatable the way cups/tracks/missions
    are above - same limitation TestCharacterUnlockOrder already documents. Instead
    verifies create_items() actually produces the right number of non-free kart items
    (kart_unlock_order[1:] - see __init__.create_items) - a pool-content assertion, not
    a reachability one. Unlike Characters' own equivalent test, this DOES exercise
    create_items()'s bonus-pool trimming even in this "plenty of room" config - 35
    non-free karts is a much bigger ask than 11 non-free characters, and cups_all's 40
    locations (minus 7 mandatory cup items = 33 bonus capacity) isn't quite enough room
    for all 35."""
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
        self.assertEqual(len(karts), 33)  # 40 locations - 7 mandatory cup items = 33 capacity


class TestKartsWithThinCategoryNoLongerDeadlocks(MKDSTestBase):
    """Regression test for a real, provable fill deadlock found while expanding karts
    from a single "Standard Kart" item to all 36 real karts. An earlier version of this
    redesign made Karts mandatory Progression items, access-rule-gated via
    state.has_any(KARTS, player) exactly like cups/tracks/missions. That's fine for cups
    (each required cup shares its access rule with 4 tracks, giving plenty of
    simultaneously-free locations to bootstrap into) but not for a THIN category -
    missions/time trials, exactly 1 location per required instance: two DIFFERENT
    mandatory items (a kart and the category's own position-1 item) both needing the
    SAME single always-free bootstrap location is mathematically unsatisfiable, no
    matter the fill order - this exact config used to hit Fill.FillError. Deliberately
    NOT required_mission_count=1 - with only one possible mission, it's trivially
    position 0 (free), which wouldn't exercise a real non-bootstrap location at all.
    Reclassifying Karts as Useful (mirroring Characters, see items.py) fixes this by
    removing them from the access-rule graph entirely - this seed should just work
    normally now, no kart (or character) item required for anything."""
    options = {
        "goal": "missions_count",
        "randomize_mission_mode": True,
        "required_mission_count": 2,
        "required_time_trial_count": 0,
        "randomize_karts": True,
        "randomize_characters": True,
    }

    def test_goal(self) -> None:
        self.assertBeatable(False)
        mission_names = self.world.required_missions_in_order[1:]
        missions = self.get_items_by_name(mission_names)
        self.assertEqual(len(missions), 1)
        self.collect(missions)
        self.assertBeatable(True)  # no kart or character item needed for reachability at all

        # Characters + Karts sharing 1 slot of leftover capacity (2 locations - 1
        # mandatory mission item) under heavy competition (46 candidates for 1 slot) -
        # confirms this doesn't crash and produces exactly the right count.
        bonus_names = self.world.character_unlock_order[1:] + self.world.kart_unlock_order[1:]
        self.assertEqual(len(bonus_names), 46)  # 11 non-free characters + 35 non-free karts
        bonus_items = self.get_items_by_name(bonus_names)
        self.assertEqual(len(bonus_items), 1)


class TestCombination(MKDSTestBase):
    """Cups, Time Trials, and Missions are all item-gated now, so completion needs all
    three legs in full."""
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
        cup_names = self.world.required_cups_in_order[1:]
        track_names = self.world.required_time_trials_in_order[1:]
        mission_names = self.world.required_missions_in_order[1:]
        cups = self.get_items_by_name(cup_names)
        staff_ghosts = self.get_items_by_name(track_names)
        missions = self.get_items_by_name(mission_names)
        self.assertEqual(len(cups), 2)
        self.assertEqual(len(staff_ghosts), 3)
        self.assertEqual(len(missions), 5)
        self.collect(cups)
        self.collect(staff_ghosts)
        self.assertBeatable(False)  # cups + time trials alone aren't enough - missions still missing
        self.collect(missions)
        self.assertBeatable(True)


class TestCharacterUnlockOrder(MKDSTestBase):
    """Characters don't gate any location's reachability (Useful, not Progression - see
    items.py), so this can't be verified via assertBeatable the way cups/tracks/missions
    are above. Instead verifies create_items() actually produces one item per non-free
    character (character_unlock_order[1:] - see __init__.create_items) - a pool-content
    assertion, not a reachability one. Plenty of goal-required locations here (cups_all
    with no Time Trial/Mission Mode = 40) relative to the 11 character items, so none of
    them should hit create_items()'s bonus-pool trimming."""
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
