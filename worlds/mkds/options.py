# options.py
#
# Player-facing options, translated directly from Instructions.txt. See that file for
# the authoritative spec and rationale behind each rule.

from dataclasses import dataclass
from Options import Choice, Toggle, Range, PerGameCommonOptions, OptionError


class RandomizeTimeTrial(Toggle):
    """Whether Time Trial course access and staff-ghost checks are part of the randomizer.

    Off: Time Trial is entirely vanilla - no items, no checks tied to it.
    On: Time Trial courses unlock progressively via received items, and beating a
    course's staff ghost (when that course is needed for the goal) sends a check.
    """
    display_name = "Randomize Time Trial"


class RandomizeMissionMode(Toggle):
    """Whether Mission Mode is part of the randomizer.

    Off: Mission Mode is entirely vanilla - no items, no checks tied to it.
    On: missions send "- Clear" checks (when goal-required) and can be used for
    missions_count/combination goals. Missions always occupy their vanilla level slot -
    this option no longer shuffles which mission is where, only whether Mission Mode
    participates in the AP economy at all.
    """
    display_name = "Randomize Mission Mode"


class RandomizeCharacters(Toggle):
    """Whether characters are part of the randomizer.

    Off: all characters are available as in the base game - no character items in the
    pool, no checks tied to them.
    On: characters unlock one at a time as Useful items received from the multiworld.

    Either way, Mission Mode checks always send regardless of character - each mission
    uses a game-determined character, not one you choose, so this option doesn't gate
    them (see client.py's _check_mission_result).
    """
    display_name = "Randomize Characters"


class RandomizeKarts(Toggle):
    """Whether karts are part of the randomizer. All 36 real karts (see items.py) work
    for any character (matches the base game: nothing ties a kart to one character).

    Off: all karts are available as in the base game - no kart items in the pool, no
    checks tied to them.
    On: one random kart is free per seed; every other kart unlocks individually as a
    Useful item received from the multiworld, and the SPECIFIC kart you actually drive
    for a run must have been legitimately received (your free one, or one you found) for
    that run's check to send - see rules.py/client.py.

    Either way, Mission Mode checks always send regardless of kart, for the same reason
    as RandomizeCharacters above - see client.py's _check_mission_result.
    """
    display_name = "Randomize Karts"


class Goal(Choice):
    """What must be completed to finish the seed. Only the content actually needed for
    the selected goal participates in the AP item/check economy - the specific required
    subset is chosen at generation time (not left open for the player to satisfy with any
    combination during play), and everything not in that subset just follows the base
    game's own vanilla unlock progression untouched.

    combination uses whichever of required_cup_count / required_time_trial_count /
    required_mission_count are set above 0, all required together.
    """
    display_name = "Goal"
    option_mission_mode_complete = 0
    option_missions_count = 1
    option_cups_all = 2
    option_cups_count = 3
    option_time_trials_all = 4
    option_time_trials_count = 5
    option_combination = 6
    default = 2


class RequiredCupCount(Range):
    """How many cups must be won for goal cups_count, or as part of goal combination.
    0 means cups aren't part of a combination goal (ignored for non-cup goals)."""
    display_name = "Required Cup Count"
    range_start = 0
    range_end = 8
    default = 4


class RequiredTimeTrialCount(Range):
    """How many Time Trial staff ghosts must be beaten for goal time_trials_count, or as
    part of goal combination. 0 means time trials aren't part of a combination goal
    (ignored for non-time-trial goals).

    TODO: range_end should be the real total number of courses with staff ghosts (32
    if every Nitro+Retro track counts) - confirm during RAM/content mapping.
    """
    display_name = "Required Time Trial Count"
    range_start = 0
    range_end = 32
    default = 8


class RequiredMissionCount(Range):
    """How many missions must be cleared for goal missions_count, or as part of goal
    combination. 0 means missions aren't part of a combination goal (ignored for
    non-mission goals).
    """
    display_name = "Required Mission Count"
    range_start = 0
    range_end = 63  # confirmed via mkds-re: 7 levels x 9 missions each - see locations.py
    default = 20


@dataclass
class MKDSOptions(PerGameCommonOptions):
    randomize_time_trial: RandomizeTimeTrial
    randomize_mission_mode: RandomizeMissionMode
    randomize_characters: RandomizeCharacters
    randomize_karts: RandomizeKarts
    goal: Goal
    required_cup_count: RequiredCupCount
    required_time_trial_count: RequiredTimeTrialCount
    required_mission_count: RequiredMissionCount

    def validate(self) -> None:
        if self.goal == Goal.option_missions_count:
            if not self.randomize_mission_mode:
                raise OptionError("Goal 'missions_count' requires Randomize Mission Mode to not be off.")
            if self.required_mission_count.value < 1:
                raise OptionError("Goal 'missions_count' requires required_mission_count of at least 1.")

        if self.goal == Goal.option_mission_mode_complete and not self.randomize_mission_mode:
            raise OptionError("Goal 'mission_mode_complete' requires Randomize Mission Mode to not be off.")

        if self.goal == Goal.option_cups_count and self.required_cup_count.value < 1:
            raise OptionError("Goal 'cups_count' requires required_cup_count of at least 1.")

        if self.goal in (Goal.option_time_trials_count, Goal.option_time_trials_all) and not self.randomize_time_trial:
            raise OptionError("This Goal requires Time Trials, but Randomize Time Trial is off.")

        if self.goal == Goal.option_time_trials_count and self.required_time_trial_count.value < 1:
            raise OptionError("Goal 'time_trials_count' requires required_time_trial_count of at least 1.")

        if self.goal == Goal.option_combination and not (
            self.required_cup_count.value or self.required_time_trial_count.value or self.required_mission_count.value
        ):
            raise OptionError("Goal 'combination' needs at least one required_*_count option set above 0.")

        if self.required_time_trial_count.value and not self.randomize_time_trial:
            raise OptionError("required_time_trial_count is set but Randomize Time Trial is off.")

        if self.required_mission_count.value and not self.randomize_mission_mode:
            raise OptionError("required_mission_count is set but Randomize Mission Mode is off.")
