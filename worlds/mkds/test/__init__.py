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
    """Missions aren't item-gated (see rules.py module docstring) - the goal should be
    immediately beatable from an empty state, since there's nothing blocking reachability
    of the always-open mission locations."""
    options = {
        "goal": "mission_mode_complete",
        "randomize_mission_mode": "all",
        "required_time_trial_count": 0,  # avoid the "count set but category off" OptionError
    }

    def test_goal(self) -> None:
        self.assertBeatable(True)


class TestMissionsCount(MKDSTestBase):
    options = {
        "goal": "missions_count",
        "randomize_mission_mode": "non_boss_only",
        "required_mission_count": 10,
        "required_time_trial_count": 0,
    }

    def test_goal(self) -> None:
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


class TestCombination(MKDSTestBase):
    """Cups and Time Trials are both item-gated, so completion needs both in full;
    missions (also part of this combination) contribute no item gate."""
    options = {
        "goal": "combination",
        "randomize_time_trial": True,
        "randomize_mission_mode": "all",
        "required_cup_count": 3,
        "required_time_trial_count": 4,
        "required_mission_count": 6,
    }

    def test_goal(self) -> None:
        self.assertBeatable(False)
        cup_names = self.world.required_cups_in_order[1:]
        track_names = self.world.required_time_trials_in_order[1:]
        cups = self.get_items_by_name(cup_names)
        staff_ghosts = self.get_items_by_name(track_names)
        self.assertEqual(len(cups), 2)
        self.assertEqual(len(staff_ghosts), 3)
        self.collect(cups)
        self.assertBeatable(False)  # cups alone aren't enough - time trials still missing
        self.collect(staff_ghosts)
        self.assertBeatable(True)
