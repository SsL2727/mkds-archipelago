# client.py
#
# BizHawk client integration. Structure follows worlds/_bizhawk's documented pattern
# (see reference/Archipelago/worlds/_bizhawk/README.md).
#
# Status (2026-08-04, later still): race-win and mission-win detection, and mapping a
# detected win to a specific location/sending it, are both live now. Earlier this
# project targeted the USA build with an empirically-guessed RaceConfig offset
# (RACECONFIG_OFFSET_FROM_RACESTATUS) that was directly observed to be UNSTABLE -
# reading the same address twice in the same race returned different values, and one of
# the wrong values collided with an already-"confirmed" table entry (a live
# demonstration of sending a WRONG check, not just a missed one). That mechanism is gone
# entirely, not just patched - this project switched its primary target to the EU build,
# which mkds-re documents directly: RACECONFIGMANAGER_ADDRESS (rom_addresses.py) is the
# real static pointer the game itself uses, verified byte-identical across repeated
# reads and correct across multiple different races. See rom_addresses.py's RaceConfig
# section for the full incident/resolution history.
#
# Cup-win detection (_check_cup_result, "{cup} - Win") and goal completion
# (_check_goal_complete, ClientStatus.CLIENT_GOAL) were both entirely missing until
# 2026-08-04 (later still) - only individual "{track} - 1st Place" checks existed, but
# winning a Grand Prix CUP is a points-based result across all 4 races, a genuinely
# different event. _check_cup_result's mechanism (mkds-re's StructTrophyResult) is
# CONFIRMED LIVE - verified against a real completed Mushroom Cup (150cc, 1st place):
# cup_idx and player_global_rank both read exactly what was on screen, not just
# plausible-looking values. See rom_addresses.py's StructTrophyResult section for the
# full verification. _check_goal_complete reads ctx.checked_locations (server-confirmed
# state) rather than guessing at game state directly.

from collections import Counter
from typing import Optional, TYPE_CHECKING

import worlds._bizhawk as bizhawk
from worlds._bizhawk.client import BizHawkClient
from NetUtils import ClientStatus

from . import rom_addresses
from .items import item_table
from .locations import location_table, MISSION_OBJECTIVES_BY_LEVEL, CUPS

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext


class MKDSClient(BizHawkClient):
    game = "Mario Kart DS"
    system = "NDS"
    patch_suffix = ".apmkds"  # TODO: not a real patch format yet - no ROM patch exists,
    # this client currently only intends to read/write live RAM. Revisit once/if a ROM
    # patch turns out to be necessary (see NOTES.md's "read/write native struct vs. ship
    # a custom patch" open question).

    async def validate_rom(self, ctx: "BizHawkClientContext") -> bool:
        try:
            # NDS cartridge header layout confirmed via GBATEK (problemkaputt.de/gbatek-ds-
            # cartridge-header.htm), 2026-08-04: gamecode is 4 bytes at offset 0x00C,
            # uppercase ASCII. Must be read from rom_addresses.ROM_DOMAIN ("ROM"), NOT
            # rom_addresses.DOMAIN ("ARM9 System Bus") - confirmed live that the header
            # does not reliably appear at a fixed low address on the System Bus domain
            # (Instruction TCM remapping can shadow it), while the ROM domain gives it
            # directly and reliably. "AMCP" is Mario Kart DS (EU, En/Fr/De/Es/It) - this
            # project switched its primary target from USA to EU, 2026-08-04, since
            # mkds-re's decompile directly provides verified EU addresses for structures
            # (RaceConfigManager especially) that were only reachable via unreliable
            # empirical guessing for USA. Exact match required, not just a prefix, since
            # even same-alphabet regional variants (e.g. USA "AMCE") have shifted static
            # data layouts that would silently misbehave if wrongly accepted.
            game_code = (await bizhawk.read(
                ctx.bizhawk_ctx, [(0x0C, 4, rom_addresses.ROM_DOMAIN)]
            ))[0].decode("ascii", errors="replace")
            if game_code != "AMCP":
                return False
        except bizhawk.RequestFailedError:
            return False

        ctx.game = self.game
        ctx.items_handling = 0b001
        ctx.want_slot_data = True
        return True

    async def game_watcher(self, ctx: "BizHawkClientContext") -> None:
        try:
            await self._apply_received_items(ctx)
            await self._check_race_result(ctx)
            await self._check_cup_result(ctx)
            await self._check_goal_complete(ctx)
        except bizhawk.RequestFailedError:
            # Connector didn't respond - let the main loop retry.
            pass

    async def _apply_received_items(self, ctx: "BizHawkClientContext") -> None:
        """OR the bits for everything currently received into the unlock-flags word.
        Recomputes the full target mask every call (cheap, self-correcting) rather than
        trying to track incremental deltas.
        """
        received_counts = Counter(network_item.item for network_item in ctx.items_received)

        unlock_bits = 0
        for name, bit in rom_addresses.CHARACTER_UNLOCK_BITS.items():
            if received_counts.get(item_table[name].code, 0) > 0:
                unlock_bits |= bit

        # Each required cup after the first has its own directly-named item (e.g.
        # receiving "Special Cup" unlocks Special Cup) - see items.py's header comment
        # and rules.py's _sequence_access_rule for the full reasoning. The FIRST required
        # cup needs no item - it's the bootstrap entry point into the chain, unlocked
        # unconditionally here (index 0 in the enumerate below), matching its access rule
        # exactly (rules.py gives it `lambda state: True`). Getting the bootstrap case
        # wrong would be a real softlock if the first required cup happens to be one of
        # the 4 lockable ones (Star/Special/Leaf/Lightning) - nothing could unlock it,
        # nothing could be won to receive the item that was supposed to already be free.
        cup_order = (ctx.slot_data or {}).get("required_cups_in_order", [])
        for i, cup_name in enumerate(cup_order):
            if i == 0 or received_counts.get(item_table[cup_name].code, 0) > 0:
                unlock_bits |= rom_addresses.CUP_UNLOCK_MASKS.get(cup_name, 0)

        if unlock_bits == 0:
            return  # nothing received yet that needs unlocking

        current = (await bizhawk.read(
            ctx.bizhawk_ctx, [(rom_addresses.UNLOCK_FLAGS_ADDRESS, 4, rom_addresses.DOMAIN)]
        ))[0]
        current_value = int.from_bytes(current, "little")
        new_value = current_value | unlock_bits

        if new_value != current_value:
            await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(rom_addresses.UNLOCK_FLAGS_ADDRESS, list(new_value.to_bytes(4, "little")), rom_addresses.DOMAIN)],
                [(rom_addresses.UNLOCK_FLAGS_ADDRESS, current, rom_addresses.DOMAIN)],
            )
        # TODO: Karts and Time Trial track items are received but not applied yet -
        # karts need the "randomize starting kart assignment" mechanism (no native flag
        # exists to write - see rom_addresses.py's kart-unlock-tier notes), and Time
        # Trial has no goal leg or location data yet (see rules.py/locations.py TODOs).

    async def _check_race_result(self, ctx: "BizHawkClientContext") -> None:
        """Detects when the player finishes a race in 1st place, and sends the
        corresponding "{track} - 1st Place" check if the track's internal_course_id is
        one of the ones mapped in rom_addresses.CONFIRMED_COURSE_IDS (see that constant's
        docstring - all 32 tracks are mapped, via mkds-re's course-id lookup table rather
        than racing each one individually; an unrecognized course_id is still handled as
        "nothing to send" rather than an error, as a defense-in-depth fallback only).
        """
        if not hasattr(ctx, "mkds_seen_race_ptr"):
            ctx.mkds_seen_race_ptr = None
            ctx.mkds_race_check_sent = False

        ptr_bytes = (await bizhawk.read(
            ctx.bizhawk_ctx, [(rom_addresses.GLOBAL_MV_POINTER_ADDRESS, 4, rom_addresses.DOMAIN)]
        ))[0]
        race_status_ptr = int.from_bytes(ptr_bytes, "little")

        heap_lo, heap_hi = rom_addresses.HEAP_RANGE
        if not (heap_lo <= race_status_ptr <= heap_hi):
            # Not a plausible heap pointer - no race currently active.
            ctx.mkds_seen_race_ptr = None
            ctx.mkds_race_check_sent = False
            return

        if race_status_ptr != ctx.mkds_seen_race_ptr:
            # New race instance (freshly (re)allocated) - reset per-race dedup state.
            ctx.mkds_seen_race_ptr = race_status_ptr
            ctx.mkds_race_check_sent = False

        if ctx.mkds_race_check_sent:
            pass  # already handled whatever this race's outcome was - still fall through
            # to _check_mission_result below, mission and race checks are independent.
        else:
            fields = await bizhawk.read(ctx.bizhawk_ctx, [
                (race_status_ptr + rom_addresses.RACESTATUS_OFFSET_RACE_ENDED, 4, rom_addresses.DOMAIN),
                (race_status_ptr + rom_addresses.RACESTATUS_OFFSET_PLACE_DRIVER_IDS, 8, rom_addresses.DOMAIN),
            ])
            race_ended = int.from_bytes(fields[0], "little")
            place_driver_ids = fields[1]

            # Require place_driver_ids to be a genuine permutation of 0-7, not just the
            # right byte length - a real multi-racer Grand Prix result should always be
            # one; a degenerate Time Trial state (no real CPU opponents) is less likely to
            # accidentally satisfy this, which is a useful (if soft) signal this was
            # actually a Grand Prix finish. Unlike the old empirical-offset mechanism, a
            # Time Trial result slipping through here wouldn't read course_id from a
            # wrong address - RACECONFIGMANAGER_ADDRESS is a single direct pointer,
            # correct for every mode - so this is a plausibility filter, not a
            # correctness dependency.
            is_real_placement = len(place_driver_ids) == 8 and sorted(place_driver_ids) == list(range(8))
            if race_ended and is_real_placement and place_driver_ids[0] == rom_addresses.PLAYER_DRIVER_ID:
                ctx.mkds_race_check_sent = True
                course_id = await self._read_internal_course_id(ctx)
                track_name = rom_addresses.CONFIRMED_COURSE_IDS.get(course_id)
                required_tracks = (ctx.slot_data or {}).get("required_race_tracks", [])
                if track_name is not None and track_name in required_tracks:
                    location_name = f"{track_name} - 1st Place"
                    location_id = location_table[location_name].code
                    await ctx.send_msgs([{"cmd": "LocationChecks", "locations": [location_id]}])

        await self._check_mission_result(ctx, race_status_ptr)

    async def _check_cup_result(self, ctx: "BizHawkClientContext") -> None:
        """Detects an overall Grand Prix CUP win (Gold trophy) and sends the
        corresponding "{cup} - Win" check - a DIFFERENT event from _check_race_result's
        individual "{track} - 1st Place" (a cup's result is a points total across all 4
        races, so winning the cup doesn't require winning every individual race, and
        vice versa). Confirmed live 2026-08-04 against a real completed Mushroom Cup -
        see rom_addresses.py's StructTrophyResult section for the verification.
        """
        if not hasattr(ctx, "mkds_seen_trophy_ptr"):
            ctx.mkds_seen_trophy_ptr = None
            ctx.mkds_cup_check_sent = False

        ptr_bytes = (await bizhawk.read(
            ctx.bizhawk_ctx, [(rom_addresses.GLOBAL_TROPHY_RESULT_POINTER_ADDRESS, 4, rom_addresses.DOMAIN)]
        ))[0]
        trophy_ptr = int.from_bytes(ptr_bytes, "little")

        # Deliberately NOT a HEAP_RANGE check (unlike GLOBAL_MV_POINTER_ADDRESS above) -
        # a real playtest (2026-08-04) completed a cup and got no check, and the only
        # live confirmation this address ever had was a single sample from one specific
        # test run. HEAP_RANGE's bounds were never independently verified for THIS
        # pointer's target - a different navigation history before reaching the trophy
        # screen could plausibly land the allocation somewhere HEAP_RANGE doesn't cover,
        # which would silently and consistently skip every poll with no error, matching
        # exactly what was reported. What IS solidly confirmed live is that this address
        # reads exactly 0x00000000 when no ceremony is showing - checking against that
        # specific signature is both looser (less likely to reject a real pointer) and
        # better-evidenced than a guessed range. The cup_idx/player_global_rank check
        # just below is the real plausibility gate on the DATA itself.
        if trophy_ptr == 0:
            # No trophy ceremony currently showing (null pointer).
            ctx.mkds_seen_trophy_ptr = None
            ctx.mkds_cup_check_sent = False
            return

        if trophy_ptr != ctx.mkds_seen_trophy_ptr:
            # New trophy ceremony instance - reset per-ceremony dedup state.
            ctx.mkds_seen_trophy_ptr = trophy_ptr
            ctx.mkds_cup_check_sent = False

        if ctx.mkds_cup_check_sent:
            return

        fields = await bizhawk.read(ctx.bizhawk_ctx, [
            (trophy_ptr + rom_addresses.TROPHYRESULT_OFFSET_CUP_IDX, 2, rom_addresses.DOMAIN),
            (trophy_ptr + rom_addresses.TROPHYRESULT_OFFSET_PLAYER_GLOBAL_RANK, 2, rom_addresses.DOMAIN),
        ])
        cup_idx = int.from_bytes(fields[0], "little")
        player_rank = int.from_bytes(fields[1], "little")
        if not (0 <= cup_idx <= 7 and 0 <= player_rank <= 7):
            return  # doesn't look like real trophy data yet (struct may still be initializing)

        result_table = (await bizhawk.read(
            ctx.bizhawk_ctx, [(rom_addresses.RACER_POSITION_TO_CUP_RESULT_TABLE_ADDRESS, 8, rom_addresses.DOMAIN)]
        ))[0]
        cup_result = result_table[player_rank]

        ctx.mkds_cup_check_sent = True
        if cup_result != rom_addresses.CUP_RESULT_GOLD:
            return  # ceremony seen, but not a win - nothing to send

        cup_name = CUPS[cup_idx]
        required_cups = (ctx.slot_data or {}).get("required_cups_in_order", [])
        if cup_name in required_cups:
            location_data = location_table[f"{cup_name} - Win"]
            await ctx.send_msgs([{"cmd": "LocationChecks", "locations": [location_data.code]}])

    async def _read_race_config_base(self, ctx: "BizHawkClientContext") -> Optional[int]:
        """Dereferences RACECONFIGMANAGER_ADDRESS to the live RaceConfigManager base
        (cur_race - the actual active race's RaceConfig - is at offset 0 of this; see
        rom_addresses.py's RaceConfig section). Heap-allocated, so re-read fresh every
        call rather than caching. Returns None if the pointer doesn't look
        heap-allocated, matching this module's general "skip rather than risk a wrong
        read" pattern (mirrors _check_race_result's own GLOBAL_MV_POINTER_ADDRESS check).
        """
        ptr_bytes = (await bizhawk.read(
            ctx.bizhawk_ctx, [(rom_addresses.RACECONFIGMANAGER_ADDRESS, 4, rom_addresses.DOMAIN)]
        ))[0]
        race_config_addr = int.from_bytes(ptr_bytes, "little")

        heap_lo, heap_hi = rom_addresses.HEAP_RANGE
        if not (heap_lo <= race_config_addr <= heap_hi):
            return None
        return race_config_addr

    async def _read_internal_course_id(self, ctx: "BizHawkClientContext") -> Optional[int]:
        """Reads RaceConfig.internal_course_id via the direct RACECONFIGMANAGER_ADDRESS
        pointer (see rom_addresses.py's RaceConfig section - verified live across
        multiple races, byte-identical on repeated reads, unlike the abandoned empirical-
        offset mechanism this replaced). Also reads cup_idx as a cheap plausibility
        guard (real races always have cup_idx 0-7) and returns None if it's out of
        range, purely as defense in depth - callers already treat a None/unrecognized
        course_id as "nothing to send", not an error.
        """
        race_config_addr = await self._read_race_config_base(ctx)
        if race_config_addr is None:
            return None

        fields = await bizhawk.read(ctx.bizhawk_ctx, [
            (race_config_addr + rom_addresses.RACECONFIG_OFFSET_INTERNAL_COURSE_ID, 4, rom_addresses.DOMAIN),
            (race_config_addr + rom_addresses.RACECONFIG_OFFSET_CUP_IDX, 4, rom_addresses.DOMAIN),
        ])
        course_id = int.from_bytes(fields[0], "little")
        cup_idx = int.from_bytes(fields[1], "little")
        if not (0 <= cup_idx <= 7):
            return None
        return course_id

    async def _check_mission_result(self, ctx: "BizHawkClientContext", race_status_ptr: int) -> None:
        """Detects a Mission Mode win via DriverStatus_Flags_MissionRunWinDelay (bit 4 of
        flags_and_respawn_id) on the player's own DriverStatus entry - confirmed by
        research (mkds-re's enum), not yet independently live-verified against an actual
        mission attempt. Sends only the "- Clear" check - "- 3 Stars" needs the mission's
        `rank` field (StructMissionLevelStageInfo, per NOTES.md), whose live address
        hasn't been found yet. Reads cur_mission_level/cur_mission_stage via the same
        direct RACECONFIGMANAGER_ADDRESS pointer as _read_internal_course_id. Known
        consequence: a goal requiring "- 3 Stars" on any mission can never actually reach
        CLIENT_GOAL yet (_check_goal_complete waits for every required location to be
        checked) - individual mission clears still detect and send correctly regardless.
        """
        if not hasattr(ctx, "mkds_mission_win_seen"):
            ctx.mkds_mission_win_seen = False

        driver_addr = (
            race_status_ptr
            + rom_addresses.RACESTATUS_OFFSET_DRIVERS_ARRAY
            + rom_addresses.PLAYER_DRIVER_ID * rom_addresses.DRIVERSTATUS_SIZE
        )
        flags_bytes = (await bizhawk.read(
            ctx.bizhawk_ctx,
            [(driver_addr + rom_addresses.DRIVERSTATUS_OFFSET_FLAGS_AND_RESPAWN_ID, 4, rom_addresses.DOMAIN)],
        ))[0]
        flags = int.from_bytes(flags_bytes, "little")
        won = bool(flags & rom_addresses.DRIVERSTATUS_FLAG_MISSION_WIN_DELAY)

        if won and not ctx.mkds_mission_win_seen:
            ctx.mkds_mission_win_seen = True
            race_config_addr = await self._read_race_config_base(ctx)
            if race_config_addr is not None:
                level_stage = await bizhawk.read(ctx.bizhawk_ctx, [
                    (race_config_addr + rom_addresses.RACECONFIG_OFFSET_CUR_MISSION_LEVEL, 1, rom_addresses.DOMAIN),
                    (race_config_addr + rom_addresses.RACECONFIG_OFFSET_CUR_MISSION_STAGE, 1, rom_addresses.DOMAIN),
                ])
                level, stage = level_stage[0][0], level_stage[1][0]
                if 0 <= level < len(MISSION_OBJECTIVES_BY_LEVEL) and 0 <= stage < len(MISSION_OBJECTIVES_BY_LEVEL[level]):
                    objective = MISSION_OBJECTIVES_BY_LEVEL[level][stage]
                    mission_name = f"Level {level + 1} Mission {stage + 1} - {objective}"
                    required_missions = (ctx.slot_data or {}).get("required_missions", [])
                    if mission_name in required_missions:
                        location_data = location_table[f"{mission_name} - Clear"]
                        await ctx.send_msgs([{"cmd": "LocationChecks", "locations": [location_data.code]}])
        elif not won:
            ctx.mkds_mission_win_seen = False

    async def _check_goal_complete(self, ctx: "BizHawkClientContext") -> None:
        """Sends ClientStatus.CLIENT_GOAL once every goal-required location is
        server-confirmed checked (ctx.checked_locations) - reconstructs the exact same
        required-location-name set rules.py's decide_goal_requirements computed at
        generation time, from the same four lists already exposed via slot_data, rather
        than tracking completion separately client-side. Deliberately reads
        ctx.checked_locations (server state, kept in sync by the framework) instead of
        our own send-confirmation bookkeeping, so this stays correct even across a
        reconnect where past sends wouldn't otherwise be remembered.

        Honest limitation, not a bug: mission goals need both "- Clear" AND "- 3 Stars"
        per required mission (rules.py's completion_condition), and Time Trial goals
        need "- Staff Ghost Beaten" - neither mission rank nor Time Trial ghost-beat
        detection exists yet (see _check_mission_result and rom_addresses.py's "still
        unmapped" section), so a goal depending on either can track individual progress
        but can never actually satisfy this check yet. Cup-only goals (cups_all/
        cups_count, the default) work fully today - _check_cup_result is confirmed live.
        """
        if getattr(ctx, "mkds_goal_sent", False):
            return

        slot_data = ctx.slot_data or {}
        required_cups = slot_data.get("required_cups_in_order", [])
        required_tracks = slot_data.get("required_race_tracks", [])
        required_time_trials = slot_data.get("required_time_trials_in_order", [])
        required_missions = slot_data.get("required_missions", [])
        if not (required_cups or required_tracks or required_time_trials or required_missions):
            return  # slot_data not populated yet (not connected, or nothing is goal-required)

        required_location_names = (
            {f"{cup} - Win" for cup in required_cups}
            | {f"{track} - 1st Place" for track in required_tracks}
            | {f"{track} - Staff Ghost Beaten" for track in required_time_trials}
            | {f"{mission} - Clear" for mission in required_missions}
            | {f"{mission} - 3 Stars" for mission in required_missions}
        )
        required_location_ids = {location_table[name].code for name in required_location_names}

        if required_location_ids <= ctx.checked_locations:
            ctx.mkds_goal_sent = True
            await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
