# rom_addresses.py
#
# Confirmed and partially-confirmed RAM addresses for Mario Kart DS (EU, En/Fr/De/Es/It -
# gamecode AMCP), read/written via BizHawk's "ARM9 System Bus" memory domain. See
# NOTES.md (project root) for the full investigation history, methodology, and confidence
# level behind each entry - this file only carries the conclusions.
#
# REGION SWITCH (2026-08-04, later still): this project targeted the USA build (AMCE) for
# most of its development, using EMPIRICALLY-PORTED addresses (guessed offsets from the
# EU addresses below, then live-verified) since mkds-re only documents EU directly. That
# approach proved unreliable for the single most important address (RaceConfigManager -
# see NOTES.md's extensive incident log) - readings that looked individually plausible
# turned out to sometimes be unstable or flat wrong, in ways no cheap sanity check fully
# caught. Switched the primary target to EU instead, once an EU ROM became available:
# mkds-re's addresses work DIRECTLY, with no porting/guessing needed, and every one
# checked so far has been immediately reliable (byte-identical across repeated reads,
# correct across multiple different races) in exactly the way the ported USA addresses
# were not. validate_rom (client.py) now requires "AMCP" specifically.
#
# MAJOR SOURCE: github.com/XorTroll/mkds-re, a reverse-engineered decompile of the EU
# build (headers + linker symbols for struct layouts and global addresses). Struct field
# OFFSETS are used directly; global addresses are ALSO now used directly (no porting).

DOMAIN = "ARM9 System Bus"

# For reading the raw cartridge header (game code, title) specifically - NOT the same as
# DOMAIN above. Confirmed 2026-08-04: the header does NOT reliably appear at a fixed low
# address on "ARM9 System Bus" (that region can be shadowed by Instruction TCM remapping -
# address 0x0 there showed stable ARM opcodes, not header text, across multiple fresh
# reboots). The "ROM" domain gives the real header directly (verified: "MARIOKARTDS" title
# and "AMCP" gamecode both read correctly at their GBATEK-documented offsets via this
# domain). Use this domain specifically for header/gamecode checks.
ROM_DOMAIN = "ROM"

# --- Master unlock-flags word (empirically verified by direct read/write testing) -----
# A single 32-bit bitfield. Only read by the game when a menu SCREEN LOADS - writing it
# while already sitting on the affected menu has no visible effect until you back out
# and back in (or otherwise force the screen to reload).
#
# *** CONFIRMED WORKING ON EU, UNCHANGED FROM THE USA VALUE (2026-08-04) *** - same
# absolute address, no porting needed. Verified live: wrote UNLOCK_MASK_EVERYTHING here
# (no reboot in between - see the dedicated warning below), then forced a menu reload by
# backing out of Character Select and back in. Result confirmed across all three relevant
# screens: Character Select showed the 4 bonus characters (Daisy/Waluigi/R.O.B./Dry Bones)
# alongside the 8 starters, Kart Select's counter read "1/36" (all karts, up from the
# default 1/2), and Cup Select showed all 8 cups (Nitro + Retro Grand Prix) instead of
# just the 4 default-unlocked ones. This confirms the ENTIRE bit map mapped during the
# original USA bisection work (below) carries over to EU unchanged - none of that
# granular per-bit work needs to be redone.
#
# *** IMPORTANT - REBOOT WIPES UNSAVED WRITES HERE ***: an earlier same-day test wrote
# this same value, then queued REBOOT before screenshotting - result showed the untouched
# 8-starter baseline, wrongly suggesting the hypothesis was false. Root cause: BizHawk's
# `client.reboot_core()` reloads RAM from the last SAVED .sav state, discarding any
# not-yet-saved raw memory write - it does NOT preserve live RAM the way a mid-session
# menu-reload does. Retesting the identical write WITHOUT an intervening reboot (just a
# back-out/back-in menu reload) immediately showed the expected unlock effect. Lesson:
# never REBOOT between a write-test and its verification unless the write is also
# expected to survive a save reload - the two are testing genuinely different things.
UNLOCK_FLAGS_ADDRESS = 0x023CE2E0  # confirmed identical on EU, 2026-08-04

UNLOCK_MASK_STAR_CUP_GROUP = 0x0000000F          # bits 0-3: Star Cup (exact bit TBD)
UNLOCK_MASK_SPECIAL_CUP_GROUP = 0x00000070       # bits 4-6: Special Cup (exact bit TBD)
UNLOCK_MASK_LEAF_LIGHTNING_GROUP = 0x00003F80    # bits 7-13: Leaf Cup + Lightning Cup together (superseded by the two individual bits below - kept for reference)
UNLOCK_BIT_LEAF_CUP = 0x00000100                 # bit 8 - individually confirmed
UNLOCK_BIT_LIGHTNING_CUP = 0x00001000            # bit 12 - individually confirmed
# Bits 7, 9, 10, 11, 13 within the old "group" tested individually as inert (7, 10, 11)
# or untested (9, 13) - likely unused/reserved. Not chasing further, group behavior is
# now fully explained by the two real bits above.
UNLOCK_BIT_MIRROR_MODE = 0x00010000              # bit 16 ALONE - confirmed by itself, no bit 15 needed
UNLOCK_MASK_LIGHTNING_ALT_PATH = 0x00014000      # bits 14+16 together: a SECOND, unexplained path to Lightning Cup
UNLOCK_MASK_DRY_BONES_GROUP = 0x001E0000         # bits 17-20: Dry Bones (+ correlated "all karts unlocked" side effect, cause unconfirmed)
UNLOCK_BIT_DAISY = 0x00200000                    # bit 21 - individually confirmed
UNLOCK_BIT_WALUIGI = 0x00400000                  # bit 22 - individually confirmed
UNLOCK_BIT_ROB = 0x00800000                      # bit 23 - individually confirmed
# Bits 24-26 unaccounted for - the Daisy/Waluigi/R.O.B. group turned out to fit entirely
# in bits 21-23, so 24-26 are still unknown (unused/reserved, or something not yet found).

UNLOCK_MASK_EVERYTHING = 0x07FFFFFF  # matches the known community "unlock everything" AR cheat

# Item-name -> unlock-bit mappings for client.py's item-receiving logic. Only covers
# individually-isolated bits/masks - see the honest gaps noted per entry.
CHARACTER_UNLOCK_BITS = {
    "Daisy": UNLOCK_BIT_DAISY,
    "Waluigi": UNLOCK_BIT_WALUIGI,
    "R.O.B.": UNLOCK_BIT_ROB,
    # Dry Bones: only the 4-bit GROUP mask is known, not which single bit within it is
    # really "Dry Bones" (the other 3 may be unused/reserved, or may not be). Using the
    # whole group as a pragmatic stand-in - setting extra unused bits should be harmless,
    # but this hasn't been proven safe by isolating them individually.
    "Dry Bones": UNLOCK_MASK_DRY_BONES_GROUP,
}
# The 8 starter characters (Mario, Luigi, Peach, Yoshi, Toad, Donkey Kong, Wario, Bowser)
# are always available and don't need an unlock bit at all.

CUP_UNLOCK_MASKS = {
    "Star Cup": UNLOCK_MASK_STAR_CUP_GROUP,
    "Special Cup": UNLOCK_MASK_SPECIAL_CUP_GROUP,
    "Leaf Cup": UNLOCK_BIT_LEAF_CUP,          # individually isolated 2026-08-04, no longer shares a group
    "Lightning Cup": UNLOCK_BIT_LIGHTNING_CUP,  # ditto
}
# Mushroom Cup, Flower Cup, Shell Cup, Banana Cup are always available and don't need an
# unlock bit at all.

# Cups unlocked by default on a fresh save (need no flag bit): Mushroom, Flower, Shell,
# Banana. Characters available by default: the 8 starters (Mario, Luigi, Peach, Yoshi,
# Toad, Donkey Kong, Wario, Bowser).
#
# mkds-re's SecretFlags enum documents a DIFFERENT, more tightly-packed bit layout
# (Star=bit0, Special=bit1, Leaf=bit2, Lightning=bit3, Mirror=bit4, DryBones=bit5,
# Daisy=bit6, Waluigi=bit7, R.O.B.=bit8, extra-karts tiers=bits9-11) that does NOT match
# our empirically-verified spread-out bits above. Not a contradiction: that enum belongs
# to `StructM.unlocked_secret_flags`, a TRANSIENT value computed by
# `GetCurrentUnlockedSecretFlags()` for driving the "you unlocked something!" popup UI -
# not the persistent save representation. Our empirical UNLOCK_FLAGS_ADDRESS findings are
# directly write-tested and confirmed working; treat them as authoritative for actually
# controlling unlock state. The enum is still useful confirmation of the overall item set
# and unlock semantics (see mkds-re re-export/include/mkds-eu-types.h ~line 195).

# --- Kart unlock system (confirmed via mkds-re - NOT a per-kart flag system) ----------
# `enum ExtraKartUnlockState`: Invalid=0, NothingUnlocked=1, BasicUnlock=2, MediumUnlock=3,
# TotalUnlock=4. `enum CharacterKartUnlockFlags`: None=0, ExtraKartsBasicUnlock=2,
# ExtraKartsMediumUnlock=4, ExtraKartsTotalUnlock=8. This is a definitive, authoritative
# confirmation of what we suspected from empirical testing (unlocking characters cascaded
# to "all karts unlocked"): kart availability is governed by a coarse 4-TIER progress
# state, not an individual per-kart flag. Functions `SetMKDSSVExtraKartUnlockFlagsByState`
# / `CheckExtraKartUnlockFlags` / `CheckExtraKartUnlockFlagsWith` exist in the EU symbol
# table (not yet address-verified for USA) and are the real mechanism - strengthens the
# case for our planned approach (patch each character's *starting kart assignment*
# directly) rather than trying to find/fake a native per-kart flag that doesn't exist.
#
# Live tier-VALUE address: NOT found nearby UNLOCK_FLAGS_ADDRESS (tried, 2026-08-04).
# Multi-round NARROWSTART/TOGGLE (3 full A/B rounds, varied timing) directly writing/
# unwriting UNLOCK_MASK_DRY_BONES_GROUP at UNLOCK_FLAGS_ADDRESS - no menu navigation, pure
# memory write - across the whole 0x800-byte region around it: converged to exactly ONE
# surviving candidate, and that one was trivial (0x023CE2E2, just the upper byte of the
# write itself, i.e. observing my own input, not a real discovery). Conclusion: whatever
# derived tier value the game actually uses is NOT cached anywhere near the flags word
# and does not update from a passive write - consistent with the already-documented "only
# read when a menu screen loads" behavior of UNLOCK_FLAGS_ADDRESS itself. Finding the real
# tier value (if that's ever needed - see the kart design fork notes elsewhere in this
# file) would need the navigation-based version of this test (write the flag, navigate to
# a screen that actually consults it like Character/Kart Select, then search) - not
# attempted today, deliberately deferred given demonstrated navigation fragility this
# session (see NOTES.md). This negative result is worth keeping so a future attempt
# doesn't re-try the cheap nearby-search first.

# --- Time Trial track access (researched 2026-08-04 - NOT a per-track flag either) -----
# Same shape of problem as karts above, found via general web research rather than
# mkds-re this time (no relevant function names turned up in the decompile - "which
# course IDs does time trial mode consider selectable" logic wasn't isolated). Confirmed
# community knowledge: in vanilla MKDS, which tracks you can even SELECT in Time Trial
# mode is derived entirely from Grand Prix cup-unlock state (win a cup -> its 4 tracks
# become time-trial-selectable) - there is no separate, individual per-track unlock flag
# to find or write. This almost certainly means Time Trial course access reads the exact
# same UNLOCK_FLAGS_ADDRESS bits already fully mapped for cups above, not a new address.
# (Separately, actually BEATING a course's staff ghost - relevant to this world's
# "{track} - Staff Ghost Beaten" locations - has its own vanilla prerequisite of getting
# within 108% of the staff time first; that's a real skill gate outside AP's control,
# same as actually winning a cup requires real driving, not something to patch around.)
#
# This creates the same item/mechanism granularity mismatch as karts: items.py has one
# unlock item per individual track (per Instructions.txt's "Time Trials: Progressive" -
# granularity wasn't specified further, one-per-track was our own default guess), but
# the native mechanism only supports unlocking in GROUPS OF 4 (one
# group per cup, matching cup-unlock granularity) - there's no way to unlock exactly one
# specific track's time trial independent of its cup-mates without an ASM-level patch to
# whatever check currently derives time-trial-selectability from cup state. Not blocking
# anything built so far - rules.py's goal-logic layer (access rules, completion
# conditions) is a pure logical abstraction that doesn't care how client.py eventually
# implements the real unlock, so this is purely a client.py-implementation-time question,
# not a rules.py design mistake to undo. Flagging clearly rather than silently picking an
# approach, same reasoning as the kart design fork above - this changes shipped
# granularity for an item category Instructions.txt explicitly sized at 32, worth the
# user's input if/when this becomes the active blocker rather than more solo guessing.

# --- Race state: RaceStatus / DriverStatus (VERIFIED against this EU ROM, 2026-08-04) --
# g_GlobalMV: a static global pointer that always points to the CURRENT RaceStatus
# instance while a race is active (heap-allocated, so the target address varies race to
# race - always dereference this pointer fresh, never hardcode a target address).
# Using mkds-re's EU address directly - verified live (plausible time_frame_counter,
# time_running=1, stable/identical across repeated reads).
GLOBAL_MV_POINTER_ADDRESS = 0x0217561C  # dereference this (4 bytes, LE) to get the live RaceStatus base address

# RaceStatus field offsets (from the pointer above). Struct is 0x524 bytes total.
# Verified live: time_frame_counter/time_running plausible, finished_driver_count matched
# real state (7 CPUs finished while player was idle), and place_driver_ids read back as a
# clean permutation of 0-7 - strong, multi-field confirmation this layout is correct.
RACESTATUS_OFFSET_TIME_FRAME_COUNTER = 0x0     # u32, frames elapsed
RACESTATUS_OFFSET_TIME_RUNNING = 0x4           # u32, 1 = race timer active
RACESTATUS_OFFSET_LAP_TIMER = 0x8              # RaceTime (4 bytes, internal format not decoded yet)
RACESTATUS_OFFSET_RANKTIME_GP_VAL = 0xC        # u16
RACESTATUS_OFFSET_FINISHED_DRIVER_COUNT = 0xE  # u16 - how many of the 8 drivers have finished
RACESTATUS_OFFSET_DRIVERS_ARRAY = 0x14         # DriverStatus[8], 0x8C (140) bytes each - see below
RACESTATUS_OFFSET_PLACE_DRIVER_IDS = 0x474     # u8[8] - place_driver_ids[0] = driver ID currently in 1st, etc.
RACESTATUS_OFFSET_RACE_ENDED = 0x4CC           # u32
RACESTATUS_OFFSET_MISSION_RESULT = 0x4E0       # u32 - Mission Mode win/loss result
RACESTATUS_OFFSET_ONE_OVER_LAP_COUNT = 0x4E8   # u32 - relates to total lap count for this race
RACESTATUS_OFFSET_MISSION_WIN_DELAY_COUNTER = 0x4FA   # u16
RACESTATUS_OFFSET_MISSION_LOSE_DELAY_COUNTER = 0x4FC  # u16

DRIVERSTATUS_SIZE = 0x8C  # 140 bytes; drivers[N] = RACESTATUS_OFFSET_DRIVERS_ARRAY + N * DRIVERSTATUS_SIZE
DRIVERSTATUS_OFFSET_RACE_FINISH_STATUS = 0x0   # u32
DRIVERSTATUS_OFFSET_LAP_FRAME_COUNTER = 0x4    # u32
DRIVERSTATUS_OFFSET_LAP_TIMES = 0x8            # RaceTime[6], 0x18 bytes per-lap times
DRIVERSTATUS_OFFSET_TOTAL_TIME = 0x20          # RaceTime
DRIVERSTATUS_OFFSET_CUR_LAP = 0x24             # u32 - VERIFIED (read back 1 while player was stuck on lap 1)
DRIVERSTATUS_OFFSET_FIRST_PLACE_TIME = 0x28    # u32
DRIVERSTATUS_OFFSET_TOTAL_TIME_MS = 0x2C       # u32
DRIVERSTATUS_OFFSET_FLAGS_AND_RESPAWN_ID = 0x30  # u32 - see DriverStatus_Flags bits below
DRIVERSTATUS_OFFSET_HIGHEST_REACHED_LAP = 0x3A   # u16
DRIVERSTATUS_OFFSET_CPOI_PROGRESS = 0x40       # fx32 (fixed-point) - progress around the current checkpoint
DRIVERSTATUS_OFFSET_RACE_PROGRESS = 0x44       # fx32 - overall race completion progress
DRIVERSTATUS_OFFSET_LAP_PROGRESS = 0x48        # fx32 - progress through the current lap

# enum DriverStatus_Flags (mkds-re, confirmed 2026-08-04) - bits within the u32 at
# DRIVERSTATUS_OFFSET_FLAGS_AND_RESPAWN_ID. Only the mission-relevant ones are named here;
# not yet live-tested against an actual mission win/loss (found via research, not emulator).
DRIVERSTATUS_FLAG_IS_PLAYER = 1
DRIVERSTATUS_FLAG_WRONG_DIRECTION = 4
DRIVERSTATUS_FLAG_MISSION_WIN_DELAY = 16   # set while the "mission cleared" delay is running
DRIVERSTATUS_FLAG_MISSION_LOSE_DELAY = 32  # set while the "mission failed" delay is running
DRIVERSTATUS_FLAG_PERFORM_FINISH = 64

# Which array index in drivers[8] / place_driver_ids is "the player" - was a best-guess
# (matched a plausible cur_lap=1 read, not independently proven), NOW CONFIRMED: directly
# read RaceConfig.player_driver_id (RACECONFIG_OFFSET_PLAYER_DRIVER_ID below, via
# RACECONFIGMANAGER_ADDRESS) as 0 in two independent live races, 2026-08-04. Still a
# hardcoded constant rather than a live read in client.py today (0 for both single-player
# Grand Prix races tested) - fine for now, but if client.py ever needs this in a context
# where it could plausibly differ, read RACECONFIG_OFFSET_PLAYER_DRIVER_ID live instead
# of trusting this constant.
PLAYER_DRIVER_ID = 0  # confirmed live 2026-08-04, see caveat above

HEAP_RANGE = (0x021DA340, 0x023E0000)  # for validating a pointer looks heap-allocated

# --- Mission Mode structure (confirmed via mkds-re, 2026-08-04) -----------------------
# SaveDataSection_MissionRun: 7 levels (SaveDataMissionRunLevelEntry[7]), matching our
# earlier deduction from manual_mariokartds_xanderoni's data. Each level has 9 stage
# entries (SaveDataMissionRunLevelEntry.stage_entries[9]) - so 7*9 = 63 total mission
# slots (locations.py's MISSIONS_PER_LEVEL already reflects this). Runtime representation
# per mission (StructMissionLevelStageInfo) has two
# separate one-byte fields: `beaten` and `rank` - directly matches Instructions.txt's
# "one check for clearing, another for getting 3 stars" design. The compact SAVE FILE
# representation (SaveDataMissionRunLevelStageEntry) packs both into a single bitfield
# byte - exact bit-packing not decoded yet, but the runtime struct alone may be enough
# for client.py's live detection purposes without needing the packed save format.
MISSION_LEVEL_COUNT = 7
MISSIONS_PER_LEVEL = 9  # locations.py's MISSIONS_PER_LEVEL already matches this

# --- RaceConfig / DriverConfig full layout (struct-confirmed via mkds-re, 2026-08-04) --
# RaceConfig is 0x1E8 bytes, embedded at RaceConfigManager.cur_race (offset 0) and again
# at .next_race (offset 0x1E8) - see rom_addresses "still unmapped" note for the live
# g_RaceConfigManager address gap. Offsets below are struct-layout-confirmed (region-
# independent); this is the single most valuable struct found today - it directly answers
# "which track/cup/mission is active", "which driver index is the player" (no more
# guessing), and "which character/kart is each driver using".
RACECONFIG_OFFSET_INTERNAL_COURSE_ID = 0x0    # u32
RACECONFIG_OFFSET_CUP_IDX = 0x4               # u32
RACECONFIG_OFFSET_RACE_MODE = 0x8             # u32
RACECONFIG_OFFSET_DISPLAY_MODE = 0xC          # u32
RACECONFIG_OFFSET_CC_TYPE = 0x10              # u32 - 0/1/2 = 50/100/150cc (exact mapping TBD)
RACECONFIG_OFFSET_CPU_MODE = 0x14             # u32
RACECONFIG_OFFSET_BATTLE_TYPE = 0x18          # u32
RACECONFIG_OFFSET_COURSE_RULES = 0x1C         # u32
RACECONFIG_OFFSET_MISSION_ID = 0x2E           # u8 - which mission within the level
RACECONFIG_OFFSET_MISSION_CHARACTER_ID = 0x32 # u8
RACECONFIG_OFFSET_MISSION_KART_ID = 0x33      # u8
RACECONFIG_OFFSET_CUR_MISSION_LEVEL = 0x54    # u8 - 0-6, one of the 7 mission levels
RACECONFIG_OFFSET_CUR_MISSION_STAGE = 0x55    # u8 - 0-8, one of the 9 stages per level
RACECONFIG_OFFSET_PLAYER_DRIVER_ID = 0x62     # u8 - AUTHORITATIVE "which drivers[] index is
# the player" - once RaceConfig's live address is known, read this instead of trusting the
# PLAYER_DRIVER_ID=0 guess above.
RACECONFIG_OFFSET_RACER_ENTRIES = 0x68        # DriverConfig[8], 0x30 bytes each - see below

DRIVERCONFIG_SIZE = 0x30
DRIVERCONFIG_OFFSET_CHARACTER_ID = 0x0        # u32 - which character driver N is using
DRIVERCONFIG_OFFSET_KART_ID = 0x4             # u32 - which kart (GLOBAL id, not per-character
# slot 0-2 - see CharacterKartContext.kart_idx_mod_3 below) driver N is using THIS race.
# racer_entries[player_driver_id].kart_id is the plan's leading candidate for a kart-item
# enforcement write target (see NOTES.md's kart-assignment section for the full design
# discussion / open UX question of how the player expresses "use a specific received kart"
# beyond vanilla's per-character 3-slot picker).
DRIVERCONFIG_OFFSET_DRIVER_IDX = 0x14         # u32

# --- CharacterKartContext (mkds-re, 2026-08-04) - LIVE selection/render state, one per ---
# racer, NOT the same thing as RaceConfig's racer_entries (that's race SETUP; this is the
# on-screen character+kart preview/render state, populated as you browse character/kart
# select). EU symbol GetCharacterKart(driver_id) returns a pointer into an array of these;
# array base is StructAD00.driver_character_karts (offset 0x0) - StructAD00's own live
# address not yet found. Struct is 0xB4 bytes.
CHARKARTCTX_OFFSET_CHAR_IDX = 0x0             # u32
CHARKARTCTX_OFFSET_KART_IDX = 0x4             # u32 - GLOBAL kart id (0-35ish), independent
# of char_idx (not derived from it) - confirms the engine has no hard-coded restriction
# tying a kart_idx to one specific char_idx; "any character can use any kart" (Instructions.
# txt's "no engine-level restriction" claim) is consistent with this.
CHARKARTCTX_OFFSET_KART_IDX_MOD_3 = 0x68      # u16 - kart_idx % 3; strongly suggests global
# kart ids are laid out as character_slot*3 + (0/1/2), i.e. each character "owns" a
# contiguous block of 3 ids in the global 0-35 numbering, used for shared per-slot data
# (stats tier?) lookups - not confirmed live, inferred from the field name alone.

# --- StructB488 (mkds-re, 2026-08-04) - session/ranking record, NOT the race-setup source
# of truth. EU symbol g_GlobalB488 = 0x0217B488 (static pointer, USA address not yet
# verified - same -0x20-or-unknown-offset problem as g_RaceConfigManager below). Has
# cup_idx (0x84), cc_type (0x88), player_character_id (0x90), player_kart_id (0x94),
# racer_character_ids[8] (0xAC), racer_kart_ids[8] (0xCC) - looks WFC-ranking-oriented
# (player_global_rank, player_total_rankpoints nearby) rather than canonical race config.
# Useful as a secondary cross-check if RaceConfig's address search stalls, but RaceConfig
# (via RaceConfigManager) is the better primary target - it's the actual race-setup input,
# not a derived record of it.

# --- RaceConfig live address - RESOLVED for real via the direct EU static pointer -------
# g_RaceConfigManager (mkds-re) used directly, no porting or offset-guessing:
RACECONFIGMANAGER_ADDRESS = 0x021759C0  # dereference this (4 bytes, LE) to get the live RaceConfigManager base address; cur_race (RaceConfig) is at offset 0
#
# This REPLACES the entire "empirical offset from RaceStatus" mechanism used during the
# USA-targeting phase of this project (see NOTES.md for that full, ultimately-abandoned
# investigation - it's kept there as history, not repeated here). That approach measured
# a fixed byte offset between two independently-allocated heap structures and hoped the
# gap stayed constant; it didn't (confirmed via multiple contradictory live readings,
# including one that silently produced a WRONG-but-plausible-looking value that collided
# with a different real track). Dereferencing RACECONFIGMANAGER_ADDRESS directly has none
# of that risk - it's the actual global pointer the game itself uses, not an inferred
# relationship between two other things.
#
# Verified live, 2026-08-04: two different races (Mushroom Cup/Figure-8 Circuit and
# Flower Cup/Desert Hills), both giving fully self-consistent, correct data - cup_idx
# exactly matching the selected cup (0 and 1 respectively), internal_course_id distinct
# and stable between the two tracks (20 and 27), player_driver_id=0 both times, AND (unlike
# every USA attempt) all 8 racer_entries slots showing clean, plausible, distinct
# character_id/kart_id values with no garbage - a full 0-7 character_id permutation each
# race. Re-read the same address twice in immediate succession with nothing in between:
# byte-for-byte identical both times (the USA mechanism failed this exact test).
#
# internal_course_id is at RaceConfig offset 0 (i.e. directly at this dereferenced
# address + 0, same as before); cup_idx at +4, etc. - see RACECONFIG_OFFSET_* below,
# unchanged (struct offsets were always region-independent).

# course_id (RaceConfig.internal_course_id, i.e. InternalCourseId in mkds-re) -> track
# name. COMPLETE for all 32 tracks, 2026-08-04 - not built up empirically race-by-race
# after all. Two entries (20, 27) were independently live-confirmed by actually racing
# (see above); while chasing whether Time Trial's course_id updates live as the menu
# cursor moves between tracks (it does NOT - internal_course_id only reflects the
# actual currently-loaded race, confirmed by cursoring to Yoshi Falls and reading an
# unchanged value of 20), found a much better source instead of testing the other 30
# live one at a time.
#
# mkds-re declares TWO parallel course-numbering schemes, easy to conflate:
#   - `CourseId` (0-31): UI/save-file order - track N's ghost/best-time record slot.
#     Exactly matches TRACKS_BY_CUP's flattened order (independently confirms both
#     sources - one web-sourced, one decompiled - agree on all 32 track identities).
#   - `InternalCourseId` (0-54): the engine's actual course-loading id - this is what
#     RaceConfig.internal_course_id (and therefore RACECONFIGMANAGER_ADDRESS) uses.
#     Includes non-race entries interspersed (battle stages, cut/test tracks, staff
#     roll, award ceremony) - NOT a simple offset from CourseId.
# `g_InternalCourseIdOrderedTable[32]` (EU address 0x02154128, static ROM data - always
# readable, no dereferencing needed) is the game's own CourseId -> InternalCourseId
# lookup table: index with CourseId (i.e. TRACKS_BY_CUP's flattened position), get back
# the real internal_course_id. Read live via READAT and cross-checked THREE ways: (1)
# every one of the 32 values matches its expected codename in mkds-eu-types.h's
# InternalCourseId enum (e.g. table[0]=20, and InternalCourseId 20 is literally named
# `cross_course` - "cross" describing a figure-8's crossed shape), (2) table[0]=20 and
# table[4]=27 exactly match the two independently live-race-confirmed values above, (3)
# CourseId's own enum names, in order, match TRACKS_BY_CUP's flattened track order
# name-for-name. All 32 agree - about as solid as static analysis plus live spot-checks
# can get without individually racing all 32.
CONFIRMED_COURSE_IDS = {
    1: "GCN Yoshi Circuit",
    9: "GCN Baby Park",
    10: "SNES Mario Circuit 1",
    11: "N64 Moo Moo Farm",
    12: "GBA Bowser Castle 2",
    13: "GBA Peach Circuit",
    14: "GCN Luigi Circuit",
    15: "SNES Koopa Beach 2",
    16: "N64 Frappe Snowland",
    17: "Tick-Tock Clock",
    18: "Luigi's Mansion",
    19: "Airship Fortress",
    20: "Figure-8 Circuit",       # live-race-confirmed (Mushroom Cup)
    22: "Yoshi Falls",
    23: "N64 Banshee Boardwalk",
    24: "Shroom Ridge",
    25: "Mario Circuit",
    26: "Peach Gardens",
    27: "Desert Hills",           # live-race-confirmed (Flower Cup)
    28: "Delfino Square",
    29: "Rainbow Road",
    30: "DK Pass",
    31: "Cheep Cheep Beach",
    32: "Bowser's Castle",
    33: "Waluigi Pinball",
    34: "Wario Stadium",
    35: "SNES Donut Plains 1",
    36: "N64 Choco Mountain",
    37: "GBA Luigi Circuit",
    38: "GCN Mushroom Bridge",
    39: "SNES Choco Island 2",
    40: "GBA Sky Garden",
}

# Time Trial mode: confirmed live 2026-08-04 that RaceConfig.internal_course_id does
# NOT update as the course-select cursor moves between tracks (stayed at Figure-8's 20
# while the screen visibly showed Yoshi Falls highlighted) - it only reflects the
# actually-loaded race, same as Grand Prix. RACECONFIGMANAGER_ADDRESS itself is a single
# global not specific to any mode, so once a Time Trial run is actually active it should
# read correctly with no separate mechanism needed - just don't trust it while still
# browsing menus, for either mode. Not yet live-verified from an actual running Time
# Trial (only checked the course-select menu), but nothing suggests it would differ from
# Grand Prix's already-confirmed behavior once a race is truly loaded. The OLD Time-
# Trial-specific empirical offset (0xE0 from RaceStatus) no longer applies at all - it
# was a workaround for the old mechanism's separate, ALSO-unreliable behavior in Time
# Trial specifically, and has no equivalent need now that there's a single direct
# pointer for every mode.
COURSE_ID_ORDERED_TABLE_ADDRESS = 0x02154128  # g_InternalCourseIdOrderedTable[32] (EU) - static ROM data, CourseId (0-31, UI order) -> InternalCourseId (RaceConfig's course_id). Not needed at runtime (CONFIRMED_COURSE_IDS above already has the resolved names) - kept for reference/re-derivation only.

# --- Cup trophy result (StructTrophyResult, mkds-re) - address confirmed, VALIDITY -----
# CHECK WAS WRONG (found 2026-08-04, later still, via a real end-to-end playtest). Fills
# a real gap noticed while planning an end-to-end playtest: every existing detection
# mechanism (RaceConfig, RaceStatus) tells you about an INDIVIDUAL race or mission, but
# "winning a cup" in Grand Prix mode is a DIFFERENT, higher-level event - the 4-race
# series is scored by cumulative points, so a cup can be won without winning every
# individual race, or lost despite winning the last one. This is the mechanism client.py
# needs to send "{cup} - Win" checks at all (previously entirely unimplemented - only
# individual "{track} - 1st Place" checks existed).
#
# g_GlobalTrophyResult (EU 0x0217B200): a static pointer, same naming/pointer convention
# as the already-verified g_GlobalMV/g_RaceConfigManager, populated when the post-cup
# trophy ceremony screen displays (null while sitting in ordinary menus). Verified live
# against a real completed Mushroom Cup, 150cc, 1st place overall (gold trophy visible
# on screen): pointer read as 0x02389040; the dereferenced struct's cup_idx read 0
# (matches "Mushroom Cup" shown) and player_global_rank read 0 (matches "1st" shown) -
# both fields exactly matching what was on screen, not just plausible-looking. The
# ADDRESS itself is solid - this single sample is what got the field offsets and the
# CupResult table right.
#
# What was NOT solid: client.py originally gated this pointer on the same HEAP_RANGE
# check used for GLOBAL_MV_POINTER_ADDRESS, extrapolating from ONE sample that its
# target would always land in that range. It doesn't necessarily - a real user playtest
# completed a cup and got no check sent at all, consistent with the pointer landing
# outside HEAP_RANGE that time (different real-time play takes a very different amount
# of "preceding heap work" than my quick scripted navigation did) and being silently,
# consistently rejected for the ceremony's whole multi-second duration (game_watcher
# polls every ~0.5s per worlds/_bizhawk/context.py - ruled out "missed a brief window"
# as the explanation). Fixed by checking only `trophy_ptr == 0` (solidly confirmed as
# the real "no ceremony showing" signature) instead of a range - the cup_idx/player_
# global_rank plausibility check right after is the real data-validity gate. Not yet
# re-verified against a second live cup completion - flagging honestly rather than
# claiming more confidence than a single fix-without-a-retest earns.
GLOBAL_TROPHY_RESULT_POINTER_ADDRESS = 0x0217B200

# StructTrophyResult (0x124 bytes, mkds-re) - only the first two fields are needed.
TROPHYRESULT_OFFSET_CUP_IDX = 0x0             # u16 - matches CupId enum / locations.CUPS order (0=Mushroom..7=Lightning), same numbering already confirmed live for RaceConfig.cup_idx. Confirmed live: read 0 for a real Mushroom Cup completion.
TROPHYRESULT_OFFSET_PLAYER_GLOBAL_RANK = 0x2  # u16 - overall GP standing, 0-7 (0 = 1st). Confirmed live: read 0 for a real 1st-place finish.

# g_RacerPositionToCupResultTable[8] (EU 0x02154064): converts player_global_rank (0-7)
# to a CupResult (Gold=0/Silver=1/Bronze=2/Lost=3) - read this table live rather than
# assuming "rank 0 = win" or "top 3 = podium", since MKDS's real point-to-medal cutoffs
# aren't necessarily a simple placement threshold. Static ROM data, always readable, no
# dereferencing needed - same category as COURSE_ID_ORDERED_TABLE_ADDRESS above. Read
# live (2026-08-04): `00 01 02 03 03 03 03 03` - i.e. rank 0/1/2 (1st/2nd/3rd) map to
# Gold/Silver/Bronze respectively and every other rank (4th-8th) maps to Lost, a sensible
# real design (only true podium finishes earn a trophy) and exactly the kind of nuance
# that justifies reading this table instead of hardcoding a threshold. table[0]=Gold
# matches the real Mushroom Cup 1st-place run's visible gold trophy exactly.
RACER_POSITION_TO_CUP_RESULT_TABLE_ADDRESS = 0x02154064
CUP_RESULT_GOLD = 0
CUP_RESULT_SILVER = 1
CUP_RESULT_BRONZE = 2
CUP_RESULT_LOST = 3

# --- Still unmapped / not yet address-verified for EU ----------------------------------
# - g_GlobalB488 (0x0217B488, direct from mkds-re, not yet dereferenced/verified) - a
#   secondary cross-check structure, not urgent given RaceConfigManager already works.
# - Time-trial staff-ghost-beaten detection - not looked for yet, but RaceStatus's
#   drivers[]/place_driver_ids fields likely apply equally to Time Trial mode (same
#   struct), worth checking there directly rather than as a separate hunt.
# - Live mission-run struct address (equivalent of g_GlobalMV but for an active mission
#   attempt, if different from RaceStatus) - not searched for; RaceStatus's
#   mission_result/mission_win_delay_counter/mission_lose_delay_counter fields, plus
#   RaceConfig's mission_id/cur_mission_level/cur_mission_stage (now readable directly via
#   RACECONFIGMANAGER_ADDRESS), likely cover this without needing a separate structure.
# - Kart-item enforcement design (the "any character can use any unlocked kart" mode) has
#   an open UX question, not just an address gap: vanilla's kart-select UI only ever shows
#   the CURRENT character's own 3 karts (tier-gated, not per-kart-gated - see the
#   ExtraKartUnlockState notes above). Forcing the global tier to TotalUnlock makes all 3
#   of EVERY character's own karts freely browsable (cleanly solves "Yes only each
#   character's unique karts" via the existing tier system - no further address hunting
#   needed for that mode). True cross-character freedom ("Yes all") has no vanilla UI path
#   at all - it needs either an ASM-level patch to the kart-select cursor/bounds logic
#   (candidate function: CheckExtraKartUnlockFlagsWith, EU 0x02056DAC - now directly
#   usable without USA porting) or a redesign around DRIVERCONFIG_OFFSET_KART_ID (write
#   the player's actually-desired kart directly into RaceConfig.racer_entries[player_
#   driver_id] right before the race starts). The latter still needs a UI for the player
#   to EXPRESS which received kart they want, since vanilla's picker can't offer all 36.
#   Not resolved - flagging as a real design fork worth revisiting rather than a pure
#   lookup gap.
