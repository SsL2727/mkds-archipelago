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
# send, (3) a new _check_time_trial_result for Staff Ghost Beaten detection - CONFIRMED
# LIVE end-to-end 2026-08-06 (a real Time Trial finish sent its check). Mission Mode
# detection (_check_mission_result) was believed CONFIRMED LIVE as of 2026-08-06, after
# two real bugs found via a live memory probe (see that method's docstring): the win
# signal itself was a per-driver flag too transient to poll, and cur_mission_level/stage
# turned out to be 1-indexed in-game, not 0-indexed as first assumed. That confirmation
# turned out to be incomplete - a THIRD bug (missions sending their check immediately on
# start, not on completion) was still present as of 2026-08-07, reproducing on every
# mission - see _check_mission_result's own docstring for the current, still-unconfirmed
# theory and the defensive tightening + debug logging added to help diagnose it further.
#
# A separate real bug also fixed 2026-08-07: _is_run_legitimate's character/kart read
# used a hardcoded rom_addresses.PLAYER_DRIVER_ID=0 constant that turned out to be wrong
# for at least some races (false-negative legitimacy failures reported across multiple
# cups despite the player having actually received the items shown) - see
# _read_player_driver_id's docstring for the fix (read RaceConfig.player_driver_id LIVE
# instead of trusting the constant). A second, bigger contributor to that same symptom
# was found right after: validate_rom's items_handling was 0b001 ("other worlds" only),
# silently missing every self-found Character/Kart item - see validate_rom's own comment.
#
# FOUR MORE real bugs found and fixed the same day (2026-08-07), all from direct live
# playtesting after the above shipped:
# (1) _check_cup_result identified the WRONG cup after winning Lightning Cup (and
#     separately, Banana Cup) - both misidentified as Mushroom Cup. TROPHYRESULT_OFFSET_
#     CUP_IDX had only ever been confirmed against Mushroom Cup itself (idx 0), which
#     can't distinguish "reads correctly" from "always reads 0" - it was the latter. Now
#     reads cup_idx from RaceConfig instead - see that method's own THIRD bug section.
# (2) _check_mission_result could still send a check immediately on entering a mission,
#     specifically when going straight from one mission into another without leaving
#     Mission Mode, or retrying after a fail - see that method's FOURTH bug section.
# (3) _check_time_trial_result had no way to tell a Mission Mode race-end (on a track
#     that reuses a real course layout) from a genuine Time Trial finish, so completing
#     a mission set on a real track could send that track's "Staff Ghost Beaten" too -
#     see that method's own real-bug section.
# (4) _check_goal_complete relied on ctx.checked_locations directly, and a report of
#     another player's goal completion immediately goaling this player's own game (never
#     having played the needed cup) suggests that trust may not always be warranted -
#     see that method's own real-bug section for the defense-in-depth fix.

import logging
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

logger = logging.getLogger("Client")


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
        # REAL BUG FIXED 2026-08-07, per direct user report (is_run_legitimate=False
        # despite confirming both the character AND kart were actually received/unlocked,
        # driver-slot reading now separately confirmed correct via debug output): 0b001
        # only means "receive items sent from OTHER worlds" (see docs/network
        # protocol.md's items_handling table) - it does NOT include items placed within
        # THIS player's own MKDS world, which requires 0b010 as well. Every
        # Character/Kart item _is_run_legitimate checks for could be placed at ANY
        # reachable location, including this player's own (ordinary Fill placement,
        # nothing keeps a Character/Kart item out of its own world) - with only 0b001,
        # ctx.items_received silently never included any self-found copy, so
        # _is_run_legitimate's received_counts lookup would incorrectly read 0 and fail
        # legitimacy for a genuinely-received item. In a single-player game specifically,
        # ALL items are "from your own world", so 0b001 alone would receive nothing at
        # all beyond the free bootstrap entries - matching the reported "which is
        # broadly wrong across many cups/karts" symptom exactly. Now 0b111 (also adds
        # 0b100, starting inventory), matching the "receive everything" pattern already
        # used elsewhere in this codebase (see CommonClient.py's own SNIClient defaults).
        ctx.items_handling = 0b111
        ctx.want_slot_data = True

        # Force a fresh ctx.mkds_goal_confirmed_locations baseline on every (re)connect -
        # see _check_goal_complete's docstring. validate_rom runs before the server
        # handshake populates ctx.checked_locations, so this can't reseed it directly
        # here; deleting the attribute makes _record_own_check/_check_goal_complete's own
        # lazy "if not hasattr" seed logic reseed from the freshly-synced
        # ctx.checked_locations the next time either runs post-handshake, instead of
        # reusing a stale set left over from a previous connection this same process.
        if hasattr(ctx, "mkds_goal_confirmed_locations"):
            del ctx.mkds_goal_confirmed_locations

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

        Called by _check_race_result and _check_cup_result (Cups/Races) and
        _check_time_trial_result (Time Trial) - NOT by _check_mission_result anymore
        (removed 2026-08-06, per user direction): Mission Mode's character/kart are
        predetermined by the game per mission, not freely player-chosen, so this gate
        doesn't apply there - see _check_mission_result's own docstring.

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

        CONFIRMED LIVE, 2026-08-06: correctly returned False for a run as Mario on a
        seed whose free character was Daisy (Mario's item not yet received) and for a
        kart not yet granted by its placed location; correctly returned True (check
        sent) for legitimate Time Trial runs on multiple character/kart/track combos.
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

    async def _read_player_driver_id(self, ctx: "BizHawkClientContext", race_config_addr: int) -> int:
        """Reads RaceConfig.player_driver_id (RACECONFIG_OFFSET_PLAYER_DRIVER_ID, a u8)
        LIVE - the AUTHORITATIVE "which drivers[]/racer_entries[] index is the player"
        signal, per rom_addresses.py's own comment on that offset.

        REAL BUG FIXED 2026-08-07, per direct user report: every callsite here used to
        trust the hardcoded rom_addresses.PLAYER_DRIVER_ID=0 constant instead - that
        constant was only ever confirmed live for 2 races, both of which happened to read
        back 0 (see its own caveat in rom_addresses.py: "if client.py ever needs this in a
        context where it could plausibly differ, read RACECONFIG_OFFSET_PLAYER_DRIVER_ID
        live instead"). Live debug output showed is_run_legitimate=False for a Mushroom
        Cup run despite the user having actually received both the character AND kart
        items shown in that debug line - and the same false-legitimacy-failure was then
        reported on every subsequent cup, not just that one. Strong evidence the
        hardcoded 0 was reading a CPU racer's slot instead of the player's own for races
        where the player isn't grid position 0 - which also affects
        _check_race_result's own place_driver_ids lookup (same slot index decides BOTH
        "which place did the player finish in" and "which character/kart did the player
        use"), so a wrong constant here could in principle have been silently
        misidentifying finish placement too, not just character/kart legitimacy.
        """
        driver_id_bytes = (await bizhawk.read(
            ctx.bizhawk_ctx,
            [(race_config_addr + rom_addresses.RACECONFIG_OFFSET_PLAYER_DRIVER_ID, 1, rom_addresses.DOMAIN)],
        ))[0]
        return driver_id_bytes[0]

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

    async def _check_race_result(self, ctx: "BizHawkClientContext") -> None:
        """Detects when the player finishes a race in 3rd place or better, and sends the
        corresponding placement check(s) - cumulative, per user direction 2026-08-06:
        3rd or better earns "{track} - 3rd Place", 2nd or better ALSO earns "{track} -
        2nd Place", 1st ALSO earns "{track} - 1st Place" (so an actual 1st-place finish
        sends all three). Only sent if the track's internal_course_id is one of the ones
        mapped in rom_addresses.CONFIRMED_COURSE_IDS (see that constant's docstring - all
        32 tracks are mapped, via mkds-re's course-id lookup table rather than racing
        each one individually; an unrecognized course_id is still handled as "nothing to
        send" rather than an error, as a defense-in-depth fallback only), AND the
        character/kart used were legitimately received (see _is_run_legitimate).

        NOT YET LIVE-CONFIRMED for 2nd/3rd place specifically (only 1st place has been -
        see the module docstring) - please report back once tested.
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
            # place_driver_ids[i] is the driver ID currently in place i+1 (0 = 1st) - so
            # the player's OWN place is the POSITION where the player's driver ID
            # appears, not the driver ID found at some position. The previous version had
            # this backwards (used each value as an index into the array instead of
            # searching for where PLAYER_DRIVER_ID's own value sits), which only ever
            # coincidentally produced a right answer for specific permutations - found
            # and fixed 2026-08-06 while reviewing this new placement-tier code.
            #
            # player_driver_id is read LIVE (see _read_player_driver_id's docstring for
            # the real bug this fixes, 2026-08-07) rather than trusting the old hardcoded
            # rom_addresses.PLAYER_DRIVER_ID=0 constant - needed here too, not just for
            # the character/kart read below, since the wrong slot could misidentify which
            # place the player finished in.
            player_place = None
            race_config_addr = None
            player_driver_id = None
            if race_ended and is_real_placement:
                race_config_addr = await self._read_race_config_base(ctx)
                if race_config_addr is not None:
                    player_driver_id = await self._read_player_driver_id(ctx, race_config_addr)
                    logger.info(f"[MKDS debug] player_driver_id={player_driver_id}")
                    for position, driver_id in enumerate(place_driver_ids):
                        if driver_id == player_driver_id:
                            player_place = position + 1
                            break
            if race_ended and is_real_placement and player_place is not None:
                ctx.mkds_race_check_sent = True
                logger.info(
                    f"[MKDS debug] race result detected: race_ended={race_ended}, "
                    f"place_driver_ids={list(place_driver_ids)}, player_place={player_place}"
                )
                course_id = await self._read_internal_course_id(ctx)
                track_name = rom_addresses.CONFIRMED_COURSE_IDS.get(course_id)
                required_tracks = (ctx.slot_data or {}).get("required_race_tracks", [])
                logger.info(
                    f"[MKDS debug] course_id={course_id}, track_name={track_name!r}, "
                    f"required={track_name in required_tracks if track_name else False}"
                )
                if track_name is not None and track_name in required_tracks:
                    # race_config_addr/player_driver_id are guaranteed non-None here -
                    # player_place can only be non-None if that block above already ran.
                    character_name, kart_name = await self._read_driver_character_and_kart(
                        ctx, race_config_addr, player_driver_id
                    )
                    legitimate = self._is_run_legitimate(ctx, character_name, kart_name)
                    logger.info(
                        f"[MKDS debug] character={character_name!r}, kart={kart_name!r}, "
                        f"is_run_legitimate={legitimate}"
                    )
                    if legitimate:
                        # Cumulative, not exclusive - a 1st-place finish also counts
                        # as 3rd-or-better and 2nd-or-better, so all three checks send
                        # together. (Independent ifs, not elif - elif would only ever
                        # match the FIRST true branch, which since <=3 is checked
                        # first would've silently swallowed 2nd/1st place entirely;
                        # found and fixed 2026-08-06 alongside the player_place bug.)
                        locations_to_send = []
                        if player_place <= 3:
                            locations_to_send.append(f"{track_name} - 3rd Place")
                        if player_place <= 2:
                            locations_to_send.append(f"{track_name} - 2nd Place")
                        if player_place == 1:
                            locations_to_send.append(f"{track_name} - 1st Place")
                        for name in locations_to_send:
                            location_id = location_table[name].code
                            await ctx.send_msgs([{"cmd": "LocationChecks", "locations": [location_id]}])
                            self._record_own_check(ctx, location_id)
                            logger.info(f"[MKDS debug] sent check for {name!r}")

        await self._check_mission_result(ctx, race_status_ptr)
        await self._check_time_trial_result(ctx, race_status_ptr)

    async def _check_cup_result(self, ctx: "BizHawkClientContext") -> None:
        """Detects an overall Grand Prix CUP result and sends the corresponding cumulative
        checks - a DIFFERENT event from _check_race_result's individual "{track} - 1st
        Place" (a cup's result is a points total across all 4 races, so winning the cup
        doesn't require winning every individual race, and vice versa). Confirmed live
        2026-08-04 against a real completed Mushroom Cup - see rom_addresses.py's
        StructTrophyResult section for the verification.

        REDESIGNED 2026-08-06, per user direction ("make winning a cup give 3 checks as
        well"): briefly cumulative across all three cup standings (Bronze-or-better,
        Silver-or-better, Gold each independently earning their own check), mirroring
        _check_race_result's own 3rd/2nd/1st Place pattern.

        REDESIGNED AGAIN 2026-08-06, per direct user bug report ("I finish third in a
        cup and didn't receive any checks. Just make first place get 3 checks."):
        Bronze/Silver-only finishes now send NOTHING - only an actual Gold (1st place
        overall) finish sends a check, and it sends all three ("{cup} - Bronze"/
        "Silver"/"Win") together. This sidesteps whatever was wrong with the
        Bronze-alone/Silver-alone paths (never root-caused - the report was "zero
        checks", not "wrong check") rather than chasing it, since the simpler
        Gold-only-but-all-three-at-once shape was what the player actually wanted here.
        The "{cup} - Bronze"/"Silver" locations still exist and still need their own
        unlock item to be reachable (rules.py) - only the CLIENT-side send condition
        changed, not the location table or access rules.

        The character/kart validity check (_is_run_legitimate) reads RaceConfig's
        racer_entries at the moment the ceremony is detected, same as
        _check_race_result - NOT YET LIVE-VERIFIED that RaceConfig.cur_race is still the
        just-finished race's data by the time the trophy ceremony shows (plausible, since
        nothing else should have loaded in between, but unconfirmed).

        REAL BUG FIXED (found via a live memory probe, 2026-08-06, against a real
        completed Leaf Cup that got no check): the range check allowed cup_idx up to 8
        inclusive, but CUPS (locations.py) only has 8 entries, valid indices 0-7 - a
        cup_idx of exactly 8 would have made `CUPS[cup_idx]` raise IndexError, uncaught
        by this method's only try/except (which is scoped to bizhawk.RequestFailedError
        in game_watcher). Fixed to <= 7.

        SECOND REAL BUG FIXED (found via three more live probes, 2026-08-06 - Shell Cup
        and Lightning Cup both won with correct gold/legitimate data yet produced zero
        debug output, meaning this method was returning before even its first log line):
        GLOBAL_TROPHY_RESULT_POINTER_ADDRESS dereferences to the SAME heap address across
        completely different cup ceremonies within one play session (confirmed live -
        Leaf, Shell, and Lightning Cup ceremonies all read trophy_ptr=0x02389040), so the
        old "trophy_ptr != last-seen-pointer" dedup could never detect a NEW ceremony
        after the first one it ever saw - once mkds_cup_check_sent latched True for cup
        A, every later cup B/C/etc. read the exact same trophy_ptr and got silently
        skipped by the `if ctx.mkds_cup_check_sent: return` guard, forever, for the rest
        of the session. (The trophy_ptr==0 "no ceremony showing" reset was meant to catch
        this in between ceremonies, but apparently doesn't reliably fire either - not
        confirmed why, only that relying on it was wrong in practice.) Dedup is now keyed
        on the (cup_idx, player_rank) VALUE PAIR itself instead of pointer identity - a
        genuinely different cup or placement is a different pair regardless of what
        address it's stored at, and re-reading the SAME already-handled pair on
        subsequent polls (the common case, since the results screen doesn't change frame
        to frame) is now what gets skipped instead. Debouncing (needing the same pair on
        two consecutive polls before acting, from the first fix) is preserved and applies
        BEFORE checking against the already-processed pair.

        THIRD REAL BUG FIXED, 2026-08-07, per direct user report: winning Lightning Cup
        (and separately, Banana Cup) both sent/logged "Mushroom Cup" instead. Root cause:
        TROPHYRESULT_OFFSET_CUP_IDX (StructTrophyResult's own cup_idx field) was NEVER
        actually confirmed against any cup other than Mushroom Cup itself (idx 0) - see
        its own comment in rom_addresses.py, "Confirmed live: read 0 for a real Mushroom
        Cup completion" - which is indistinguishable from "always reads 0 regardless of
        input", exactly the trap that turned out to be true. This ALSO silently broke the
        (cup_idx, player_rank) dedup key above: with cup_idx stuck at 0, two DIFFERENT
        cups finishing with the SAME player_rank would look like the exact same
        already-processed pair, meaning a later cup could be silently skipped entirely
        rather than misidentified - a second, worse consequence of the same bug. Fixed by
        reading cup_idx from RaceConfig instead (RACECONFIG_OFFSET_CUP_IDX, via the same
        race_config_addr already relied on for character/kart legitimacy at this exact
        moment - the user's own report confirmed "the car and driver are correct" at
        ceremony time, which is direct live evidence RaceConfig's data is still valid and
        fresh then, so its cup_idx should be equally trustworthy). This read now happens
        BEFORE the debounce/dedup check (not after, as character/kart legitimacy does),
        since the dedup key itself now depends on it.
        """
        if not hasattr(ctx, "mkds_cup_last_processed_result"):
            ctx.mkds_cup_last_processed_result = None
            ctx.mkds_cup_pending_result = None

        ptr_bytes = (await bizhawk.read(
            ctx.bizhawk_ctx, [(rom_addresses.GLOBAL_TROPHY_RESULT_POINTER_ADDRESS, 4, rom_addresses.DOMAIN)]
        ))[0]
        trophy_ptr = int.from_bytes(ptr_bytes, "little")

        # Deliberately NOT a HEAP_RANGE check (unlike GLOBAL_MV_POINTER_ADDRESS above) -
        # confirmed live that this address reads exactly 0x00000000 before any ceremony
        # has ever shown this session. Whether it reliably returns to 0 BETWEEN later
        # ceremonies is unconfirmed (see docstring above) - this is used only as a cheap
        # "probably nothing to look at" fast path, not as the correctness guarantee;
        # cup_idx/player_global_rank plausibility plus the already-processed check below
        # are what actually protect against acting on stale/idle data.
        if trophy_ptr == 0:
            ctx.mkds_cup_pending_result = None
            return

        fields = await bizhawk.read(ctx.bizhawk_ctx, [
            (trophy_ptr + rom_addresses.TROPHYRESULT_OFFSET_PLAYER_GLOBAL_RANK, 2, rom_addresses.DOMAIN),
        ])
        player_rank = int.from_bytes(fields[0], "little")
        if not (0 <= player_rank <= 7):
            ctx.mkds_cup_pending_result = None
            return  # doesn't look like real trophy data yet (struct may still be initializing)

        # cup_idx: read from RaceConfig, NOT StructTrophyResult's own (unreliable - see
        # THIRD bug above) field.
        race_config_addr = await self._read_race_config_base(ctx)
        if race_config_addr is None:
            ctx.mkds_cup_pending_result = None
            return
        cup_idx_bytes = (await bizhawk.read(
            ctx.bizhawk_ctx, [(race_config_addr + rom_addresses.RACECONFIG_OFFSET_CUP_IDX, 4, rom_addresses.DOMAIN)],
        ))[0]
        cup_idx = int.from_bytes(cup_idx_bytes, "little")
        if not (0 <= cup_idx <= 7):
            ctx.mkds_cup_pending_result = None
            return

        current_result = (cup_idx, player_rank)
        if current_result == ctx.mkds_cup_last_processed_result:
            return  # already decided this exact outcome - avoid re-processing every poll

        if ctx.mkds_cup_pending_result != current_result:
            # Seen for the first time this poll - don't trust it yet (see docstring's
            # first fix). Wait for the NEXT poll to confirm the exact same pair.
            ctx.mkds_cup_pending_result = current_result
            return

        logger.info(f"[MKDS debug] cup result confirmed stable: cup_idx={cup_idx}, player_rank={player_rank}")

        result_table = (await bizhawk.read(
            ctx.bizhawk_ctx, [(rom_addresses.RACER_POSITION_TO_CUP_RESULT_TABLE_ADDRESS, 8, rom_addresses.DOMAIN)]
        ))[0]
        cup_result = result_table[player_rank]
        logger.info(f"[MKDS debug] cup_result={cup_result} (GOLD=0)")

        ctx.mkds_cup_last_processed_result = current_result
        if cup_result == rom_addresses.CUP_RESULT_LOST:
            return  # ceremony seen, but not a podium finish - nothing to send

        cup_name = CUPS[cup_idx]
        required_cups = (ctx.slot_data or {}).get("required_cups_in_order", [])
        logger.info(
            f"[MKDS debug] cup_name={cup_name!r}, required_cups={required_cups!r}, "
            f"in_required={cup_name in required_cups}"
        )
        if cup_name not in required_cups:
            return

        # race_config_addr already read above (needed for cup_idx) - reuse instead of
        # re-reading.
        player_driver_id = await self._read_player_driver_id(ctx, race_config_addr)
        logger.info(f"[MKDS debug] player_driver_id={player_driver_id}")
        character_name, kart_name = await self._read_driver_character_and_kart(
            ctx, race_config_addr, player_driver_id
        )
        legitimate = self._is_run_legitimate(ctx, character_name, kart_name)
        logger.info(
            f"[MKDS debug] character={character_name!r}, kart={kart_name!r}, is_run_legitimate={legitimate}"
        )
        if not legitimate:
            return

        # Gold-only, per the second redesign above - Bronze/Silver-only finishes send
        # nothing; an actual win sends all three cup locations together.
        if cup_result != rom_addresses.CUP_RESULT_GOLD:
            return

        locations_to_send = [f"{cup_name} - Bronze", f"{cup_name} - Silver", f"{cup_name} - Win"]
        for location_name in locations_to_send:
            location_data = location_table.get(location_name)
            logger.info(f"[MKDS debug] location_name={location_name!r}, found_in_table={location_data is not None}")
            if location_data is not None:
                await ctx.send_msgs([{"cmd": "LocationChecks", "locations": [location_data.code]}])
                self._record_own_check(ctx, location_data.code)
                logger.info(f"[MKDS debug] sent check for {location_name!r}")

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
        """Detects a Mission Mode win via RaceStatus.mission_win_delay_counter
        (RACESTATUS_OFFSET_MISSION_WIN_DELAY_COUNTER, a u16 on RaceStatus itself - NOT
        per-driver) being nonzero. Sends the "- Clear" check (only - "3 Stars" tracking
        was dropped entirely, see locations.py/rules.py) unconditionally once the mission
        is confirmed goal-required. Reads cur_mission_level/cur_mission_stage via the
        same direct RACECONFIGMANAGER_ADDRESS pointer as _read_internal_course_id.

        Character/kart legitimacy REMOVED here, 2026-08-06, per user direction - unlike
        Cups/Races/Time Trials (freely player-chosen), Mission Mode's character/kart are
        predetermined by the game itself per mission (see mariokart.fandom.com/wiki/
        Mission_Mode - "only the starting characters each in their respective standard
        karts"), not something the player picks to legitimize, so gating on _is_run_
        legitimate no longer applies here. (This also retires the PopTracker "out of
        logic" mission overlay feature, which existed specifically to warn about this
        gate - see mkds-poptracker/README.md.)

        CONFIRMED LIVE end-to-end, 2026-08-06, after two real bugs found via a live
        memory probe (reference/ram_probe/probe.lua's READPTR command) against a real
        completed mission's results screen:
        (1) Originally kept a DriverStatus.flags_and_respawn_id bit
        (DRIVERSTATUS_FLAG_MISSION_WIN_DELAY) on the player's own driver-array slot. The
        probe showed that bit had ALREADY cleared back to 0 by the time this method could
        poll it (confirmed driver_id=0 was in fact the right slot - its IS_PLAYER bit was
        set - the bit itself is just too transient to catch by polling).
        RACESTATUS_OFFSET_MISSION_WIN_DELAY_COUNTER, by contrast, read a stable nonzero
        value across two probes taken seconds apart on that same results screen - this is
        what's used now, and it also means player_driver_id/the drivers[8] array aren't
        needed for mission win-detection at all anymore.
        (2) cur_mission_level/cur_mission_stage turned out to be 1-indexed in-game
        (level=1 IS "Level 1"), not 0-indexed as first assumed - a live win read back
        level=1/stage=1, confirmed by playtest to be "Level 1 Mission 1", not "Level 2
        Mission 2" as the old +1 formula produced. MISSION_OBJECTIVES_BY_LEVEL itself is
        still a plain 0-indexed Python list (see locations.py), so the raw 1-indexed
        values need -1 to index it, while the DISPLAY name uses them directly.

        Resets mkds_mission_win_seen whenever race_status_ptr changes (a new race/mission
        instance), not just when the counter reads back to 0 - guards against the
        possibility that this counter doesn't reset to 0 between attempts (unconfirmed
        either way; resetting on the instance boundary is correct regardless).

        REAL BUG FIXED, 2026-08-06, per direct user report ("some mission send a check
        when starting not completing"): a freshly-allocated RaceStatus's
        mission_win_delay_counter isn't reliably zero for every mission - for at least
        some of them, the very first read after entering already comes back nonzero
        (originally assumed to be leftover heap content, not a real win). Fixed by
        requiring an explicit CONFIRMED-ZERO reading for this race_status_ptr before a
        nonzero reading is ever trusted as a real win (mkds_mission_zero_confirmed,
        reset alongside mkds_mission_win_seen on every new instance).

        STILL BROKEN as of 2026-08-07, per direct user report ("missions are sending
        their check when the mission is started instead of after completion") - the
        "confirmed-zero" guard above did not hold. The FIRST attempted fix (require
        several consecutive zero polls instead of just one) was also shipped and ALSO
        did not hold. User-supplied debug output finally identified the real root cause:
        `[MKDS debug] mission win detected: level=255, stage=255` - 255 is not a valid
        level/stage (MISSION_LEVEL_COUNT=7, MISSIONS_PER_LEVEL=9), and the user
        separately confirmed these debug lines were appearing WHILE NOT EVEN IN A
        MISSION. This method was called unconditionally every tick regardless of game
        mode (game_watcher -> _check_race_result -> _check_mission_result, using
        whatever race_status_ptr happens to be active for ANY current race type), so
        RACESTATUS_OFFSET_MISSION_WIN_DELAY_COUNTER was being read - and trusted - even
        during Grand Prix/Time Trial races where that offset's contents mean something
        else entirely (or nothing at all). REAL FIX 2026-08-07: read cur_mission_level/
        cur_mission_stage FIRST, unconditionally, and only proceed with the win-delay
        counter (and all its dedup/confirmation bookkeeping) when they're in valid
        range - i.e. only trust this signal while genuinely inside Mission Mode. This
        directly explains BOTH halves of the reported bug: the false-positive lines the
        user saw came from a NON-mission race context where the "counter" was
        meaningless data, and any dedup state a false positive left behind is no longer
        possible to accidentally carry into a real mission attempt, since
        mkds_mission_win_seen/zero_confirmed/zero_streak are now reset (not just left
        alone) on every tick spent outside Mission Mode, not only when race_status_ptr
        changes.

        FOURTH REAL BUG FIXED, 2026-08-07, per direct user report: entering a NEW
        mission right after another, without ever leaving Mission Mode entirely (level/
        stage go straight from one valid mission to another, never through the invalid-
        255 "not in mission" state above), or retrying the SAME mission after failing
        it, could still send a check immediately on entry. Two contributing bugs fixed
        together:
        (1) The reset above only fired on a `race_status_ptr` change - if the game
        reuses the same RaceStatus allocation across back-to-back missions (plausible,
        since you never leave Mission Mode's own menu flow), a genuinely NEW mission
        (different level/stage) wouldn't reset the dedup state at all. Now keyed on
        (race_status_ptr, level, stage) together - ANY of the three changing resets.
        (2) Once `mkds_mission_zero_confirmed` became True, it stayed true FOREVER for
        that key (only a full reset ever cleared it) - so after a real mission's
        legitimate zero-then-nonzero win sequence played out once, literally ANY later
        nonzero blip sharing that same key (e.g. a failed attempt's own end-of-attempt
        sequence, or a retry's brief startup blip, neither of which necessarily changes
        the key) would be trusted immediately, with no fresh confirmation required. Now
        `zero_confirmed` is consumed (reset to False) on EVERY poll where the counter
        reads nonzero, whether or not that poll actually resulted in a send - a fresh
        MISSION_ZERO_CONFIRM_THRESHOLD-poll streak of zeros is required before trusting
        the NEXT nonzero reading, every time, not just once per key. This is a real
        improvement (removes a genuine "confirm once, trust forever" bug) but - given
        two previous attempts at this same underlying issue each missed something -
        NOT claimed to fully resolve the retry-after-fail case, since without a live
        probe there's no way to confirm failing a mission doesn't ALSO trigger the same
        counter (in which case the true fix would need a way to distinguish WIN from
        LOSE that hasn't been found yet). Please retest and share a fresh debug log
        covering a fail+retry sequence specifically if this is still wrong.
        """
        race_config_addr = await self._read_race_config_base(ctx)
        if race_config_addr is None:
            return

        if not hasattr(ctx, "mkds_mission_win_seen"):
            ctx.mkds_mission_win_seen = False
            ctx.mkds_mission_seen_key = None
            ctx.mkds_mission_zero_confirmed = False
            ctx.mkds_mission_zero_streak = 0

        level_stage = await bizhawk.read(ctx.bizhawk_ctx, [
            (race_config_addr + rom_addresses.RACECONFIG_OFFSET_CUR_MISSION_LEVEL, 1, rom_addresses.DOMAIN),
            (race_config_addr + rom_addresses.RACECONFIG_OFFSET_CUR_MISSION_STAGE, 1, rom_addresses.DOMAIN),
        ])
        level, stage = level_stage[0][0], level_stage[1][0]
        in_mission = 1 <= level <= len(MISSION_OBJECTIVES_BY_LEVEL) and 1 <= stage <= len(MISSION_OBJECTIVES_BY_LEVEL[level - 1])

        if not in_mission:
            # Not currently in Mission Mode at all - RACESTATUS_OFFSET_MISSION_WIN_DELAY_
            # COUNTER is meaningless here (see docstring). Reset every tick, not just on a
            # key change, so nothing from outside Mission Mode can leak into a later real
            # mission attempt.
            ctx.mkds_mission_seen_key = None
            ctx.mkds_mission_win_seen = False
            ctx.mkds_mission_zero_confirmed = False
            ctx.mkds_mission_zero_streak = 0
            return

        mission_key = (race_status_ptr, level, stage)
        if mission_key != ctx.mkds_mission_seen_key:
            ctx.mkds_mission_seen_key = mission_key
            ctx.mkds_mission_win_seen = False
            ctx.mkds_mission_zero_confirmed = False
            ctx.mkds_mission_zero_streak = 0

        win_delay_bytes = (await bizhawk.read(
            ctx.bizhawk_ctx,
            [(race_status_ptr + rom_addresses.RACESTATUS_OFFSET_MISSION_WIN_DELAY_COUNTER, 2, rom_addresses.DOMAIN)],
        ))[0]
        win_delay_value = int.from_bytes(win_delay_bytes, "little")
        won = win_delay_value > 0

        MISSION_ZERO_CONFIRM_THRESHOLD = 3  # consecutive in-mission zero polls required
        if won:
            ctx.mkds_mission_zero_streak = 0
        else:
            ctx.mkds_mission_zero_streak += 1
            if ctx.mkds_mission_zero_streak >= MISSION_ZERO_CONFIRM_THRESHOLD:
                ctx.mkds_mission_zero_confirmed = True

        logger.info(
            f"[MKDS debug] mission poll: level={level}, stage={stage}, "
            f"win_delay_value={win_delay_value}, won={won}, "
            f"zero_streak={ctx.mkds_mission_zero_streak}, "
            f"zero_confirmed={ctx.mkds_mission_zero_confirmed}, "
            f"win_seen={ctx.mkds_mission_win_seen}"
        )

        if won and not ctx.mkds_mission_win_seen and ctx.mkds_mission_zero_confirmed:
            ctx.mkds_mission_win_seen = True
            objective = MISSION_OBJECTIVES_BY_LEVEL[level - 1][stage - 1]
            mission_name = f"Level {level} Mission {stage} - {objective}"
            required_missions = (ctx.slot_data or {}).get("required_missions_in_order", [])
            if mission_name in required_missions:
                location_name = f"{mission_name} - Clear"
                location_data = location_table[location_name]
                await ctx.send_msgs([{"cmd": "LocationChecks", "locations": [location_data.code]}])
                self._record_own_check(ctx, location_data.code)
                logger.info(f"[MKDS debug] sent check for {location_name!r}")
        elif not won:
            ctx.mkds_mission_win_seen = False

        if won:
            # Consume/invalidate - see FOURTH bug above. A fresh streak of zero polls is
            # required before the NEXT nonzero reading can be trusted again, even within
            # this same (ptr, level, stage) key.
            ctx.mkds_mission_zero_confirmed = False

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

        End-of-run detection: Time Trial has no CPU racers, so _check_race_result's own
        is_real_placement permutation check (which Grand Prix relies on) never fires for
        it. This method instead treats "race_ended, NOT a real Grand-Prix-shaped
        place_driver_ids, for a course_id matching a required Time Trial track, with at
        most 1 driver finished" as the signal. Believed CONFIRMED LIVE end-to-end,
        2026-08-06, on multiple tracks/character/kart combos.

        REAL BUG FIXED 2026-08-07, per direct user report: completing "Level 6 Mission 6"
        (a Mission Mode stage that takes place ON the real GCN Yoshi Circuit track) ALSO
        sent "GCN Yoshi Circuit - Staff Ghost Beaten", despite the player never having
        run an actual Time Trial there. Root cause: this method's own end-of-run signal
        (race ended, not Grand-Prix-shaped, <=1 finished driver) is equally satisfiable by
        a Mission Mode race ending on a track that happens to reuse one of the 32 real
        course layouts - nothing here previously checked that we were actually IN Time
        Trial mode as opposed to Mission Mode. Fixed by adding the same in_mission gate
        _check_mission_result uses (cur_mission_level/cur_mission_stage in valid range) -
        bail immediately if genuinely inside a mission, mirroring that method's own THIRD
        bug fix exactly. This also happens to explain a second reported symptom (Mission
        4-9 "didn't send a check on completion but PopTracker showed it complete") if
        that mission's own win-delay-counter false-positive (see
        _check_mission_result's FOURTH bug) fired early while this method's un-gated
        Time-Trial check was ALSO incidentally satisfied around the same moment - not
        confirmed, but no longer possible either way now that both paths are gated.
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

        race_config_addr = await self._read_race_config_base(ctx)
        if race_config_addr is None:
            return

        level_stage = await bizhawk.read(ctx.bizhawk_ctx, [
            (race_config_addr + rom_addresses.RACECONFIG_OFFSET_CUR_MISSION_LEVEL, 1, rom_addresses.DOMAIN),
            (race_config_addr + rom_addresses.RACECONFIG_OFFSET_CUR_MISSION_STAGE, 1, rom_addresses.DOMAIN),
        ])
        level, stage = level_stage[0][0], level_stage[1][0]
        in_mission = 1 <= level <= len(MISSION_OBJECTIVES_BY_LEVEL) and 1 <= stage <= len(MISSION_OBJECTIVES_BY_LEVEL[level - 1])
        if in_mission:
            return  # a Mission Mode race-end, not a real Time Trial run - see docstring

        fields = await bizhawk.read(ctx.bizhawk_ctx, [
            (race_status_ptr + rom_addresses.RACESTATUS_OFFSET_RACE_ENDED, 4, rom_addresses.DOMAIN),
            (race_status_ptr + rom_addresses.RACESTATUS_OFFSET_PLACE_DRIVER_IDS, 8, rom_addresses.DOMAIN),
            (race_status_ptr + rom_addresses.RACESTATUS_OFFSET_FINISHED_DRIVER_COUNT, 2, rom_addresses.DOMAIN),
        ])
        race_ended = int.from_bytes(fields[0], "little")
        place_driver_ids = fields[1]
        finished_driver_count = int.from_bytes(fields[2], "little")
        is_real_placement = len(place_driver_ids) == 8 and sorted(place_driver_ids) == list(range(8))
        if not race_ended or is_real_placement:
            return  # not ended, or looks like a real Grand Prix finish instead (see docstring)
        if finished_driver_count > 1:
            return  # more than one driver finished - not a solo Time Trial run

        course_id = await self._read_internal_course_id(ctx)
        track_name = rom_addresses.CONFIRMED_COURSE_IDS.get(course_id)
        if track_name is None or track_name not in required_tracks:
            return

        # player_driver_id read LIVE (see _read_player_driver_id's docstring, 2026-08-07
        # fix) rather than the old hardcoded rom_addresses.PLAYER_DRIVER_ID=0 constant -
        # Time Trial has no CPU opponents so this was less likely to differ from 0 in
        # practice, but there's no reason to trust the constant here either now that it's
        # confirmed unreliable elsewhere. race_config_addr already read above (needed for
        # the in_mission gate) - reuse instead of re-reading.
        player_driver_id = await self._read_player_driver_id(ctx, race_config_addr)

        driver_addr = (
            race_status_ptr
            + rom_addresses.RACESTATUS_OFFSET_DRIVERS_ARRAY
            + player_driver_id * rom_addresses.DRIVERSTATUS_SIZE
        )
        time_bytes = (await bizhawk.read(
            ctx.bizhawk_ctx,
            [(driver_addr + rom_addresses.DRIVERSTATUS_OFFSET_TOTAL_TIME_MS, 4, rom_addresses.DOMAIN)],
        ))[0]
        finish_time = self._decode_finish_time(time_bytes)
        if finish_time > rom_addresses.STAFF_GHOST_TIMES[track_name]:
            return  # didn't beat the ghost

        ctx.mkds_tt_check_sent = True

        character_name, kart_name = await self._read_driver_character_and_kart(
            ctx, race_config_addr, player_driver_id
        )
        location_name = f"{track_name} - Staff Ghost Beaten"
        if self._is_run_legitimate(ctx, character_name, kart_name):
            location_data = location_table[location_name]
            await ctx.send_msgs([{"cmd": "LocationChecks", "locations": [location_data.code]}])
            self._record_own_check(ctx, location_data.code)

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

    def _record_own_check(self, ctx: "BizHawkClientContext", location_code: int) -> None:
        """Marks a location as confirmed via THIS client's own live game-state detection
        - called right after every LocationChecks send this file makes (races, cups,
        missions, time trials). See _check_goal_complete's docstring for why goal
        completion counts against this set instead of trusting ctx.checked_locations
        directly on every poll.
        """
        if not hasattr(ctx, "mkds_goal_confirmed_locations"):
            ctx.mkds_goal_confirmed_locations = set(ctx.checked_locations)
        ctx.mkds_goal_confirmed_locations.add(location_code)

    async def _check_goal_complete(self, ctx: "BizHawkClientContext") -> None:
        """Sends ClientStatus.CLIENT_GOAL once enough of each active category's REQUIRED
        locations show up as CONFIRMED - REDESIGNED 2026-08-06, removing a real design
        flaw (see items.py's module docstring): an earlier version counted a received
        fungible "Trophy" item instead, but since Trophy copies were ordinary shuffled
        Progression items, the fill algorithm could place any given copy at ANY reachable
        location - not necessarily the specific cup/track/mission it was "for" - so the
        goal could in principle be satisfied without the player actually completing that
        many cups/tracks/missions themselves.

        REAL BUG FIXED 2026-08-07, per direct user report ("another player goaled their
        game, and it sent me the cup I need to beat my game but instead of letting me
        play the cup to goal, it immediately goaled my game"): this used to read
        ctx.checked_locations directly on every poll - server-synced state that is
        SUPPOSED to be scoped to only this player's own checked locations per
        Archipelago's protocol (CommonClient.py's Connected/RoomUpdate handling), but
        clearly wasn't behaving that way here. Rather than rely on that scoping being
        correct (this file had no way to independently verify it, and had no debug
        logging on this path at all until now - added below for future diagnosis),
        goal-completion now counts against ctx.mkds_goal_confirmed_locations instead: a
        set seeded ONCE (via _record_own_check, on first use) from whatever
        ctx.checked_locations already contained - i.e. progress legitimately earned via
        THIS SAME client's own detection logic in a PRIOR session, which is the only way
        one of these specific top-tier locations can ever have been checked for this
        player - and grown ONLY by this client's own confirmed sends from then on. A
        location that becomes "checked" server-side mid-session through any means OTHER
        than this client's own live detection can no longer count toward the goal until
        a fresh reconnect re-establishes the baseline. This is a defense-in-depth fix
        matching the user's literal request; the underlying mechanism that let another
        player's action affect this player's checked_locations was not itself
        identified (no debug log exists for this path from before this fix), so please
        report back if this still happens - the new debug logging below should make the
        exact numbers visible next time.
        """
        if getattr(ctx, "mkds_goal_sent", False):
            return

        slot_data = ctx.slot_data or {}
        required_cups = slot_data.get("required_cups_in_order", [])
        required_time_trials = slot_data.get("required_time_trials_in_order", [])
        required_missions = slot_data.get("required_missions_in_order", [])
        if not (required_cups or required_time_trials or required_missions):
            return  # slot_data not populated yet (not connected, or nothing is goal-required)

        if not hasattr(ctx, "mkds_goal_confirmed_locations"):
            ctx.mkds_goal_confirmed_locations = set(ctx.checked_locations)
        checked = ctx.mkds_goal_confirmed_locations

        if required_cups:
            target = slot_data.get("required_cup_win_count", 0)
            done = sum(1 for cup in required_cups if location_table[f"{cup} - Win"].code in checked)
            logger.info(f"[MKDS debug] goal check: cups done={done}, target={target}")
            if done < target:
                return
        if required_time_trials:
            target = slot_data.get("required_time_trial_win_count", 0)
            done = sum(
                1 for track in required_time_trials
                if location_table[f"{track} - Staff Ghost Beaten"].code in checked
            )
            logger.info(f"[MKDS debug] goal check: time trials done={done}, target={target}")
            if done < target:
                return
        if required_missions:
            target = slot_data.get("required_mission_win_count", 0)
            done = sum(1 for mission in required_missions if location_table[f"{mission} - Clear"].code in checked)
            logger.info(f"[MKDS debug] goal check: missions done={done}, target={target}")
            if done < target:
                return

        ctx.mkds_goal_sent = True
        logger.info("[MKDS debug] goal complete - sending CLIENT_GOAL")
        await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
