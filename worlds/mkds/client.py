# client.py
#
# BizHawk client integration. Structure follows worlds/_bizhawk's documented pattern
# (see reference/Archipelago/worlds/_bizhawk/README.md).
#
# DESIGN CHANGE (2026-08-05): an extensive ASM-patch investigation to suppress vanilla's
# always-available baseline content (8 starter characters, base karts, 4 free cups - none
# of which any save flag gates) failed to find a patch point - see NOTES_ARCHIVE.md for
# the full investigation. Rather than continue chasing that, the game is now forced FULLY
# unlocked (_apply_received_items writes UNLOCK_MASK_EVERYTHING unconditionally, once -
# nothing left to incrementally restrict at the game level), and enforcement moved
# entirely to the check-sending side: every check now additionally requires that the
# character AND kart actually used for the run were legitimately received as items
# (_is_run_legitimate), not just that the cup/track/mission itself is goal-required. This
# trades "physically impossible to cheat" for "no incentive to cheat" - content is still
# technically selectable without earning it, but doing so no longer earns a check.
# Characters and Karts (both Useful, not Progression - see items.py) have NO presence in
# rules.py's access rules at all; both are "one free by name per seed, everything else
# needs its own item," enforced entirely here in _is_run_legitimate - see that method's
# own docstring, including a real fill-deadlock bug found and fixed getting to this
# design (items.py's Karts section has the full account).
#
# Race-win/mission-win/cup-win DETECTION mechanisms themselves are unchanged and remain
# solid (RACECONFIGMANAGER_ADDRESS, GLOBAL_MV_POINTER_ADDRESS, StructTrophyResult - see
# rom_addresses.py for the verification history of each). This file's changes are: (1)
# the unlock-write rewrite above, (2) a validity gate added in front of every existing
# send, (3) a new _check_time_trial_result for Staff Ghost Beaten detection - the finish-
# time decode itself is CONFIRMED LIVE (2026-08-05, two independent samples - see
# _decode_finish_time's docstring); only its end-of-run detection heuristic remains
# flagged as not yet cross-checked against a real completed run actually sending a check.

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
        """Forces the game fully unlocked - one idempotent write, completely decoupled
        from which items have actually been received (see module docstring for why).
        Recomputes/re-checks every call (cheap, self-correcting) rather than tracking
        whether it's "already been done", in case something else in the game ever
        touches this address (nothing is currently known to, but this costs nothing).
        """
        current = (await bizhawk.read(
            ctx.bizhawk_ctx, [(rom_addresses.UNLOCK_FLAGS_ADDRESS, 4, rom_addresses.DOMAIN)]
        ))[0]
        current_value = int.from_bytes(current, "little")

        if current_value != rom_addresses.UNLOCK_MASK_EVERYTHING:
            await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(rom_addresses.UNLOCK_FLAGS_ADDRESS,
                  list(rom_addresses.UNLOCK_MASK_EVERYTHING.to_bytes(4, "little")),
                  rom_addresses.DOMAIN)],
                [(rom_addresses.UNLOCK_FLAGS_ADDRESS, current, rom_addresses.DOMAIN)],
            )

    def _is_run_legitimate(
        self, ctx: "BizHawkClientContext", character_name: Optional[str],
        kart_name: Optional[str],
    ) -> bool:
        """A check only counts if BOTH the character and kart actually used were
        legitimately received as items - see module docstring for the design rationale.
        Characters and Karts are checked identically (both are "one free by name per
        seed, everything else needs its own item" - see rules.py's
        choose_character_unlock_order/choose_kart_unlock_order and items.py, where both
        are classified Useful, not Progression: neither gates a LOCATION's reachability,
        only whether a real run's check gets honored here).

        Characters: one random character is free per seed (character_unlock_order[0] in
        slot_data); every other character needs its own item. Skipped entirely when
        Randomize Characters is off this seed (character_unlock_order is then empty).
        Fixes a real bug from an early (STARTER_CHARACTERS-based) version of this check:
        it never consulted the Randomize Characters option at all, so turning that option
        off never actually removed the character requirement the way its own options.py
        docstring promised ("off = no checks tied to them").

        Karts: one random kart (of all 36 real karts - items.py's KARTS) is free per
        seed (kart_unlock_order[0]); every other kart needs its own item, checked by the
        SPECIFIC kart_name actually used (resolved by the caller via
        rom_addresses.KART_ID_TO_NAME). Skipped entirely when Randomize Karts is off.
        Supersedes two earlier designs in turn: (1) a single "Standard Kart" item that
        only ever asked "is this the driven character's own standard-tier kart"
        (rom_addresses.is_standard_kart, since removed) - the other 24 of 36 real karts
        could never legitimize a run no matter what was received; (2) a
        location-based bootstrap exemption (kart_bootstrap_exempt_locations, since
        removed) that caused a real, provable fill deadlock for thin categories
        (missions/time trials) - see items.py's Karts section for the full account.
        """
        if character_name is None:
            return False  # couldn't identify the driver - fail safe, send nothing

        received_counts = Counter(network_item.item for network_item in ctx.items_received)
        slot_data = ctx.slot_data or {}

        character_unlock_order = slot_data.get("character_unlock_order", [])
        if character_unlock_order and character_name != character_unlock_order[0]:
            char_item = item_table.get(character_name)
            if char_item is None or received_counts.get(char_item.code, 0) == 0:
                return False

        kart_unlock_order = slot_data.get("kart_unlock_order", [])
        if kart_unlock_order and kart_name != kart_unlock_order[0]:
            if kart_name is None:
                return False
            kart_item = item_table.get(kart_name)
            if kart_item is None or received_counts.get(kart_item.code, 0) == 0:
                return False

        return True

    async def _read_driver_character_and_kart(
        self, ctx: "BizHawkClientContext", race_config_addr: int, driver_id: int,
    ) -> tuple[Optional[str], Optional[str]]:
        """Grand Prix / Time Trial path: reads racer_entries[driver_id].character_id/
        .kart_id (u32 fields - DRIVERCONFIG_OFFSET_*, see rom_addresses.py) and resolves
        them via mkds-re's confirmed CharacterId/KartId enums (rom_addresses.
        CHARACTER_ID_TO_NAME / KART_ID_TO_NAME). NOT YET LIVE-VERIFIED that these read
        the PLAYER's own car during a real race the way expected - the offsets/enum
        values themselves are confirmed DATA (reliable per this project's established
        pattern), but this specific read has not been cross-checked against what's
        visibly on screen yet.
        """
        driver_addr = (
            race_config_addr
            + rom_addresses.RACECONFIG_OFFSET_RACER_ENTRIES
            + driver_id * rom_addresses.DRIVERCONFIG_SIZE
        )
        fields = await bizhawk.read(ctx.bizhawk_ctx, [
            (driver_addr + rom_addresses.DRIVERCONFIG_OFFSET_CHARACTER_ID, 4, rom_addresses.DOMAIN),
            (driver_addr + rom_addresses.DRIVERCONFIG_OFFSET_KART_ID, 4, rom_addresses.DOMAIN),
        ])
        character_id = int.from_bytes(fields[0], "little")
        kart_id = int.from_bytes(fields[1], "little")
        character_name = rom_addresses.CHARACTER_ID_TO_NAME.get(character_id)
        kart_name = rom_addresses.KART_ID_TO_NAME.get(kart_id)
        return character_name, kart_name

    async def _read_mission_character_and_kart(
        self, ctx: "BizHawkClientContext", race_config_addr: int,
    ) -> tuple[Optional[str], Optional[str]]:
        """Mission Mode path: reads mission_character_id/mission_kart_id (u8 fields,
        DIFFERENT width from the Grand Prix/Time Trial path above - RACECONFIG_OFFSET_
        MISSION_CHARACTER_ID/_KART_ID, see rom_addresses.py) - same enum resolution as
        _read_driver_character_and_kart. Also not yet live-verified.
        """
        fields = await bizhawk.read(ctx.bizhawk_ctx, [
            (race_config_addr + rom_addresses.RACECONFIG_OFFSET_MISSION_CHARACTER_ID, 1, rom_addresses.DOMAIN),
            (race_config_addr + rom_addresses.RACECONFIG_OFFSET_MISSION_KART_ID, 1, rom_addresses.DOMAIN),
        ])
        character_id = fields[0][0]
        kart_id = fields[1][0]
        character_name = rom_addresses.CHARACTER_ID_TO_NAME.get(character_id)
        kart_name = rom_addresses.KART_ID_TO_NAME.get(kart_id)
        return character_name, kart_name

    async def _check_race_result(self, ctx: "BizHawkClientContext") -> None:
        """Detects when the player finishes a race in 1st place, and sends the
        corresponding "{track} - 1st Place" check if the track's internal_course_id is
        one of the ones mapped in rom_addresses.CONFIRMED_COURSE_IDS (see that constant's
        docstring - all 32 tracks are mapped, via mkds-re's course-id lookup table rather
        than racing each one individually; an unrecognized course_id is still handled as
        "nothing to send" rather than an error, as a defense-in-depth fallback only), AND
        the character/kart used were legitimately received (see _is_run_legitimate).
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
            # to the other checks below, which are independent.
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
            # actually a Grand Prix finish - see _check_time_trial_result for the
            # Time-Trial-specific counterpart to this check.
            is_real_placement = len(place_driver_ids) == 8 and sorted(place_driver_ids) == list(range(8))
            if race_ended and is_real_placement and place_driver_ids[0] == rom_addresses.PLAYER_DRIVER_ID:
                ctx.mkds_race_check_sent = True
                course_id = await self._read_internal_course_id(ctx)
                track_name = rom_addresses.CONFIRMED_COURSE_IDS.get(course_id)
                required_tracks = (ctx.slot_data or {}).get("required_race_tracks", [])
                if track_name is not None and track_name in required_tracks:
                    location_name = f"{track_name} - 1st Place"
                    race_config_addr = await self._read_race_config_base(ctx)
                    if race_config_addr is not None:
                        character_name, kart_name = await self._read_driver_character_and_kart(
                            ctx, race_config_addr, rom_addresses.PLAYER_DRIVER_ID
                        )
                        if self._is_run_legitimate(ctx, character_name, kart_name):
                            location_id = location_table[location_name].code
                            await ctx.send_msgs([{"cmd": "LocationChecks", "locations": [location_id]}])

        await self._check_mission_result(ctx, race_status_ptr)
        await self._check_time_trial_result(ctx, race_status_ptr)

    async def _check_cup_result(self, ctx: "BizHawkClientContext") -> None:
        """Detects an overall Grand Prix CUP win (Gold trophy) and sends the
        corresponding "{cup} - Win" check - a DIFFERENT event from _check_race_result's
        individual "{track} - 1st Place" (a cup's result is a points total across all 4
        races, so winning the cup doesn't require winning every individual race, and
        vice versa). Confirmed live 2026-08-04 against a real completed Mushroom Cup -
        see rom_addresses.py's StructTrophyResult section for the verification.

        The character/kart validity check (_is_run_legitimate) reads RaceConfig's
        racer_entries at the moment the ceremony is detected, same as
        _check_race_result - NOT YET LIVE-VERIFIED that RaceConfig.cur_race is still the
        just-finished race's data by the time the trophy ceremony shows (plausible, since
        nothing else should have loaded in between, but unconfirmed).
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
        if cup_name not in required_cups:
            return

        location_name = f"{cup_name} - Win"
        race_config_addr = await self._read_race_config_base(ctx)
        if race_config_addr is None:
            return
        character_name, kart_name = await self._read_driver_character_and_kart(
            ctx, race_config_addr, rom_addresses.PLAYER_DRIVER_ID
        )
        if self._is_run_legitimate(ctx, character_name, kart_name):
            location_data = location_table[location_name]
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
        mission attempt. Sends the "- Clear" check (only - "3 Stars" tracking was
        dropped entirely, see locations.py/rules.py) once the character/kart used are
        confirmed legitimate. Reads cur_mission_level/cur_mission_stage via the same
        direct RACECONFIGMANAGER_ADDRESS pointer as _read_internal_course_id.
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
                    required_missions = (ctx.slot_data or {}).get("required_missions_in_order", [])
                    if mission_name in required_missions:
                        location_name = f"{mission_name} - Clear"
                        character_name, kart_name = await self._read_mission_character_and_kart(ctx, race_config_addr)
                        if self._is_run_legitimate(ctx, character_name, kart_name):
                            location_data = location_table[location_name]
                            await ctx.send_msgs([{"cmd": "LocationChecks", "locations": [location_data.code]}])
        elif not won:
            ctx.mkds_mission_win_seen = False

    async def _check_time_trial_result(self, ctx: "BizHawkClientContext", race_status_ptr: int) -> None:
        """Detects a completed Time Trial run and sends "{track} - Staff Ghost Beaten" if
        the player's own finish time beat the reference time in
        rom_addresses.STAFF_GHOST_TIMES - comparing against a hardcoded reference time,
        NOT reading real in-game staff-ghost data, per user direction (the times
        themselves are sourced from mariokart.fandom.com/wiki/Staff_Ghosts, see
        rom_addresses.py).

        Finish-time decode CONFIRMED LIVE, 2026-08-05: DriverStatus.total_time_ms (offset
        0x2C, NOT total_time at 0x20 - see rom_addresses.py) is a plain total-milliseconds
        u32, no packed format - verified by reading it right after a real Time Trial
        finish showing "1:54:042" on screen and getting exactly 114042.

        STILL NOT LIVE-VERIFIED: end-of-run detection specifically. Time Trial has no CPU
        racers, so _check_race_result's own is_real_placement permutation check (which
        Grand Prix relies on) never fires for it. This method instead treats "race_ended
        with a NON-permutation place_driver_ids, for a course_id matching a required Time
        Trial track" as the signal - plausible given what's already confirmed about Time
        Trial's place_driver_ids (all-zero, not a permutation), but not yet cross-checked
        end-to-end against a real completed run actually sending a check.
        """
        if not hasattr(ctx, "mkds_tt_seen_race_ptr"):
            ctx.mkds_tt_seen_race_ptr = None
            ctx.mkds_tt_check_sent = False

        heap_lo, heap_hi = rom_addresses.HEAP_RANGE
        if not (heap_lo <= race_status_ptr <= heap_hi):
            ctx.mkds_tt_seen_race_ptr = None
            ctx.mkds_tt_check_sent = False
            return

        if race_status_ptr != ctx.mkds_tt_seen_race_ptr:
            ctx.mkds_tt_seen_race_ptr = race_status_ptr
            ctx.mkds_tt_check_sent = False

        if ctx.mkds_tt_check_sent:
            return

        required_tracks = (ctx.slot_data or {}).get("required_time_trials_in_order", [])
        if not required_tracks:
            return  # Time Trial isn't part of this seed - nothing to check for

        fields = await bizhawk.read(ctx.bizhawk_ctx, [
            (race_status_ptr + rom_addresses.RACESTATUS_OFFSET_RACE_ENDED, 4, rom_addresses.DOMAIN),
            (race_status_ptr + rom_addresses.RACESTATUS_OFFSET_PLACE_DRIVER_IDS, 8, rom_addresses.DOMAIN),
        ])
        race_ended = int.from_bytes(fields[0], "little")
        place_driver_ids = fields[1]
        is_real_placement = len(place_driver_ids) == 8 and sorted(place_driver_ids) == list(range(8))
        if not race_ended or is_real_placement:
            return  # not ended, or looks like a real Grand Prix finish instead (see docstring)

        course_id = await self._read_internal_course_id(ctx)
        track_name = rom_addresses.CONFIRMED_COURSE_IDS.get(course_id)
        if track_name is None or track_name not in required_tracks:
            return

        driver_addr = (
            race_status_ptr
            + rom_addresses.RACESTATUS_OFFSET_DRIVERS_ARRAY
            + rom_addresses.PLAYER_DRIVER_ID * rom_addresses.DRIVERSTATUS_SIZE
        )
        time_bytes = (await bizhawk.read(
            ctx.bizhawk_ctx,
            [(driver_addr + rom_addresses.DRIVERSTATUS_OFFSET_TOTAL_TIME_MS, 4, rom_addresses.DOMAIN)],
        ))[0]
        finish_time = self._decode_finish_time(time_bytes)
        if finish_time > rom_addresses.STAFF_GHOST_TIMES[track_name]:
            return  # didn't beat the ghost

        ctx.mkds_tt_check_sent = True

        race_config_addr = await self._read_race_config_base(ctx)
        if race_config_addr is None:
            return
        character_name, kart_name = await self._read_driver_character_and_kart(
            ctx, race_config_addr, rom_addresses.PLAYER_DRIVER_ID
        )
        location_name = f"{track_name} - Staff Ghost Beaten"
        if self._is_run_legitimate(ctx, character_name, kart_name):
            location_data = location_table[location_name]
            await ctx.send_msgs([{"cmd": "LocationChecks", "locations": [location_data.code]}])

    def _decode_finish_time(self, raw: bytes) -> tuple[int, int, int]:
        """Decodes DriverStatus.total_time_ms (4-byte u32, NOT total_time - see
        rom_addresses.py) into (minutes, seconds, milliseconds), matching
        rom_addresses.STAFF_GHOST_TIMES's format for direct tuple comparison (lexical
        tuple comparison is correct here - minutes compare first, then seconds, then
        milliseconds, exactly matching real time ordering). CONFIRMED LIVE, 2026-08-05:
        this field is a plain total-milliseconds count, no packed format - see
        _check_time_trial_result's docstring for the verification.
        """
        total_ms = int.from_bytes(raw, "little")
        minutes, remainder_ms = divmod(total_ms, 60_000)
        seconds, milliseconds = divmod(remainder_ms, 1_000)
        return minutes, seconds, milliseconds

    async def _check_goal_complete(self, ctx: "BizHawkClientContext") -> None:
        """Sends ClientStatus.CLIENT_GOAL once every goal-required location is
        server-confirmed checked (ctx.checked_locations) - reconstructs the exact same
        required-location-name set rules.py's decide_goal_requirements computed at
        generation time, from the same four lists already exposed via slot_data, rather
        than tracking completion separately client-side. Deliberately reads
        ctx.checked_locations (server state, kept in sync by the framework) instead of
        our own send-confirmation bookkeeping, so this stays correct even across a
        reconnect where past sends wouldn't otherwise be remembered.

        Honest limitation, not a bug: Time Trial goals need "- Staff Ghost Beaten",
        whose detection is structurally complete but not yet functionally live (see
        _check_time_trial_result) - a goal depending on it can track individual progress
        but can't actually satisfy this check yet. Cup-only goals (cups_all/cups_count,
        the default) and mission-only goals work fully today.
        """
        if getattr(ctx, "mkds_goal_sent", False):
            return

        slot_data = ctx.slot_data or {}
        required_cups = slot_data.get("required_cups_in_order", [])
        required_tracks = slot_data.get("required_race_tracks", [])
        required_time_trials = slot_data.get("required_time_trials_in_order", [])
        required_missions = slot_data.get("required_missions_in_order", [])
        if not (required_cups or required_tracks or required_time_trials or required_missions):
            return  # slot_data not populated yet (not connected, or nothing is goal-required)

        required_location_names = (
            {f"{cup} - Win" for cup in required_cups}
            | {f"{track} - 1st Place" for track in required_tracks}
            | {f"{track} - Staff Ghost Beaten" for track in required_time_trials}
            | {f"{mission} - Clear" for mission in required_missions}
        )
        required_location_ids = {location_table[name].code for name in required_location_names}

        if required_location_ids <= ctx.checked_locations:
            ctx.mkds_goal_sent = True
            await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
