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


class RandomizeMissionMode(Choice):
    """How Mission Mode's missions are shuffled across level slots.

    off: Mission Mode is entirely vanilla - no items, no checks tied to it.
    all: every mission (including boss missions) is shuffled into one pool across all slots.
    non_boss_only: boss missions stay in their vanilla slots untouched. Only non-boss
        missions shuffle among non-boss slots.
    non_boss_and_boss_separately: non-boss missions shuffle among non-boss slots, and
        boss missions separately shuffle among boss slots, but the two groups never mix.
    """
    display_name = "Randomize Mission Mode"
    option_off = 0
    option_all = 1
    option_non_boss_only = 2
    option_non_boss_and_boss_separately = 3
    default = 0


class RandomizeCharacters(Toggle):
    """Whether characters are part of the randomizer.

    Off: all characters are available as in the base game - no character items in the
    pool, no checks tied to them.
    On: characters unlock one at a time as Useful items received from the multiworld.
    """
    display_name = "Randomize Characters"


class RandomizeKarts(Choice):
    """Whether karts are part of the randomizer, and whether kart choice stays tied to
    the character that originally owns it. Any character can drive any kart in the base
    game (no engine restriction) - "yes_unique_only" is a restriction this randomizer
    imposes on purpose, not a limitation of MKDS itself.

    off: karts are entirely vanilla - no items, no checks tied to them.
    yes_all: all karts in the game are pooled together regardless of original character.
        Any character can drive any kart once it's unlocked.
    yes_unique_only: each character's own karts stay grouped with that character. Only
        that character can drive their own unlocked karts.

    Requires Randomize Cups to be active. (Cups has no fully-vanilla state in this
    design, so that dependency is always satisfied today.)
    """
    display_name = "Randomize Karts"
    option_off = 0
    option_yes_all = 1
    option_yes_unique_only = 2
    default = 0


class RandomizeCups(Choice):
    """How tracks are assigned to cups. Cup unlock order is always randomized regardless
    of this setting - there is no fully-vanilla option for Cups.

    unrandomized: cup-to-track assignment stays vanilla (each cup keeps its original 4
        tracks); only which cup you unlock and the order you unlock them in are randomized.
    tracks_random_no_overlap: any track can be in any cup, but each of the 32 tracks is
        used exactly once across the 8 cups.
    tracks_random_with_overlap: any track can be in any cup, and a track may appear more
        than once across the 32 race slots (so some tracks may not appear at all).
    """
    display_name = "Randomize Cups"
    option_unrandomized = 0
    option_tracks_random_no_overlap = 1
    option_tracks_random_with_overlap = 2
    default = 0


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
    randomize_cups: RandomizeCups
    goal: Goal
    required_cup_count: RequiredCupCount
    required_time_trial_count: RequiredTimeTrialCount
    required_mission_count: RequiredMissionCount

    def validate(self) -> None:
        # Characters/Karts randomization requires Cup randomization to be active, per
        # Instructions.txt. Cups has no fully-off state in this design, so this
        # dependency can't currently be violated - documented here as an explicit
        # invariant in case Cups ever gains an off-state.

        if self.goal == Goal.option_missions_count:
            if self.randomize_mission_mode.value == RandomizeMissionMode.option_off:
                raise OptionError("Goal 'missions_count' requires Randomize Mission Mode to not be off.")
            if self.required_mission_count.value < 1:
                raise OptionError("Goal 'missions_count' requires required_mission_count of at least 1.")

        if self.goal == Goal.option_mission_mode_complete and self.randomize_mission_mode.value == RandomizeMissionMode.option_off:
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

        if self.required_mission_count.value and self.randomize_mission_mode.value == RandomizeMissionMode.option_off:
            raise OptionError("required_mission_count is set but Randomize Mission Mode is off.")
