-- autotracking.lua
--
-- Archipelago autotracking for the MKDS PopTracker pack.
--
-- REDESIGNED 2026-08-06 (first pass): Cups/Time Trial tracks/Missions moved from
-- items.json progressive items to PopTracker's real locations+sections system.
--
-- REDESIGNED AGAIN 2026-08-06 (second pass): Time Trial and Missions moved BACK to
-- items.json progressive items (map panels weren't visible/discoverable in practice).
--
-- REDESIGNED A THIRD TIME 2026-08-06, per direct user feedback after trying the above
-- live - two real problems found:
--   1. Every Cup (and consequently its Grand Prix placements) showed unlocked
--      regardless of actual state. Root cause: locations/cups.json and
--      grandPrixTracks.json had NO "access_rules" field at all - PopTracker apparently
--      defaults an omitted access_rules to always-accessible, not "unknown"/locked (not
--      explicitly documented, but confirmed live by this exact bug). Fixed with a
--      custom Lua access rule ("$mkds_cup_accessible|<name>"/
--      "$mkds_track_accessible|<name>", PopTracker's documented "$functionName|arg"
--      syntax - see doc/PACKS.md) instead of a static item-code rule, since WHICH cup is
--      this seed's free bootstrap is only known at connect time via slot_data, not at
--      pack-authoring time - a plain rule can't express that.
--   2. Time Trial/Missions showed no distinguishable state at all ("no missions or time
--      trials are showing as unlocked"). Per direct user direction ("revert to the
--      previous functioning code"), these two categories were reverted to a 2-stage
--      format - stage 0 (initial) the real course/mission icon, stage 1 the generic
--      "track.png" silhouette once checked - which turned out to be an OVER-correction:
--      it went back past an earlier, already-working 3-stage (locked/unlocked/completed)
--      design instead of just fixing the two real Cup bugs above, so it reintroduced
--      exactly the "no unlocked state" complaint it was meant to fix. Corrected the
--      following day - see the fourth pass below.
--
-- REDESIGNED A FOURTH TIME 2026-08-07, per the user pointing at that earlier-working
-- version directly ("You had the working before. Go look at the code from around 2 am
-- this morning"): Time Trial/Missions are 3-stage progressive items again - stage 0
-- (locked) is the real course/mission icon with a "grey" img_mods tint (the same "grey"
-- toggle items already use for their own disabled state), stage 1 (unlocked, not yet
-- completed) is the same icon at full color, stage 2 (completed) is the generic
-- "track.png" checked icon (see generate_pack.py's _progressive_item_3stage). Unlike the
-- 2 am version (which used generic placeholder art - "images/cup.png" etc), this reuses
-- the REAL per-track/mission artwork already integrated into the pack since then, so it's
-- additive on top of that art integration work, not a revert of it. This needed a real
-- functional fix too, not just new item stages: Time Trial/Mission unlock items are now
-- ALSO looked up via ITEM_NAME_TO_CODE (previously only Characters/Karts were - a
-- received Time Trial/Mission item was silently dropped, since nothing in this file ever
-- looked it up by name) - see PROGRESSIVE_ITEM_CODES (generated) for how onItemReceived
-- tells a progressive Time Trial/Mission item apart from a toggle Character/Kart one.
--
-- Five tracked signal groups now exist:
--   1. Character/Kart items received (items.json toggles, via AddItemHandler).
--   2. Cup items received (worlds/mkds's own individually-named Cup unlock item - no
--      items.json entry of its own, purely Lua-tracked state - see cup_unlocked below)
--      and the per-seed free bootstrap cup (slot_data's cup_bootstrap, cached on
--      connect) - both feed mkds_cup_accessible/mkds_track_accessible, the custom access
--      rule functions locations/cups.json and grandPrixTracks.json call by name.
--   3. Time Trial/Mission unlock items received, OR the per-seed free bootstrap entry
--      (slot_data's time_trial_bootstrap/mission_bootstrap, a bare name - see
--      activate_bootstrap_progressive) - both advance that item's .CurrentStage from 0
--      (locked) to 1 (unlocked), mirroring Cups' own bootstrap-or-item pattern above but
--      for an items.json progressive item instead of Lua-only state.
--   4. Cup/Grand Prix-placement LOCATIONS checked (via AddLocationHandler) - looked up in
--      LOCATION_NAME_TO_SECTION (generated), sets that section's .AvailableChestCount to
--      0 (documented PopTracker Lua API for marking a section checked).
--   5. Time Trial/Mission COMPLETION locations checked (also via AddLocationHandler, same
--      event) - looked up in LOCATION_NAME_TO_ITEM_STAGE (generated) instead, advances
--      that items.json progressive item's .CurrentStage to 2 (completed) directly.
--
-- A SIXTH signal - how many of each category's top-tier LOCATIONS have actually been
-- CHECKED (cup "- Win", track "- Staff Ghost Beaten", mission "- Clear" - looked up via
-- LOCATION_NAME_TO_PROGRESS_CATEGORY/LOCATION_ID_TO_PROGRESS_CATEGORY, generated) -
-- drives the three small progress counters ("progress_cups"/"progress_time_trial"/
-- "progress_missions", plain toggle items forced always-visible, showing "X/Y" via
-- PopTracker's :SetOverlay(string) Lua method) against each category's required win
-- count (slot_data's required_cup_win_count/required_time_trial_win_count/
-- required_mission_win_count - see worlds/mkds/rules.py's completion_condition, the
-- exact same count this mirrors).
--
-- REDESIGNED 2026-08-06 (this pass, same day as the third pass above): worlds/mkds
-- removed its fungible "Trophy" items entirely (items.py's fifth redesign pass - a real
-- design flaw the user identified: a Trophy copy could be placed by the fill algorithm
-- at ANY reachable location, not necessarily the one it was "for", so counting RECEIVED
-- Trophy items no longer means anything). This pack's progress counters used to count
-- received Trophy items the same (now-removed) way - switched to counting CHECKED
-- top-tier locations directly instead, mirroring exactly what worlds/mkds/rules.py's
-- completion_condition and client.py's _check_goal_complete actually check.
--
-- Written against PopTracker's documented Archipelago autotracking API
-- (github.com/black-sliver/PopTracker/blob/master/doc/AUTOTRACKING.md /
-- doc/PACKS.md, checked 2026-08-06): AddItemHandler's callback is (index, item_id,
-- item_name, player_number); AddLocationHandler's is (location_id, location_name);
-- AddClearHandler's is (slot_data); Archipelago.CheckedLocations is an array of
-- already-checked location ids, nil on PopTracker installs older than 0.25.2 (see
-- manifest.json's min_poptracker_version). "$functionName|arg" custom access rules call
-- a plain GLOBAL Lua function (not registered via any special API - confirmed against
-- PopTracker's own docs: "rules starting with $ will call the Lua function with that
-- name", pipe-delimited arguments). NOT YET TESTED against a real PopTracker install -
-- flagging honestly rather than claiming this works untested, matching this project's
-- established practice (see NOTES.md).

ScriptHost:LoadScript("scripts/item_name_to_code.lua")
ScriptHost:LoadScript("scripts/progressive_item_codes.lua")
ScriptHost:LoadScript("scripts/cup_accessibility.lua")
ScriptHost:LoadScript("scripts/progress_categories.lua")
ScriptHost:LoadScript("scripts/location_section_mapping.lua")
ScriptHost:LoadScript("scripts/location_item_stage_mapping.lua")

-- Which cups are currently accessible this session (cup name -> true). Rebuilt from
-- scratch on every onClear: the seed's free bootstrap cup (slot_data.cup_bootstrap) is
-- marked true immediately; every other cup is marked true only once its own unlock item
-- is received (see onItemReceived) - mirrors worlds/mkds/rules.py's set_rules exactly
-- (one bootstrap cup free, every other cup gated on its own individually-named item).
local cup_unlocked = {}

-- Called from locations/cups.json's "$mkds_cup_accessible|<name>" access rule - must be
-- a GLOBAL function (not local) for PopTracker's $-rule dispatch to find it by name.
function mkds_cup_accessible(cup_name)
    return cup_unlocked[cup_name] == true
end

-- Called from locations/grandPrixTracks.json's "$mkds_track_accessible|<name>" access
-- rule - a track's own accessibility mirrors its PARENT cup's (TRACK_TO_CUP, from
-- cup_accessibility.lua), not a separate concept of its own, matching how
-- worlds/mkds/rules.py's set_rules gates a track's placements on its parent cup's rule.
function mkds_track_accessible(track_name)
    local cup_name = TRACK_TO_CUP[track_name]
    if cup_name == nil then
        return false
    end
    return cup_unlocked[cup_name] == true
end

-- How many of each category's top-tier locations have been CHECKED this session -
-- rebuilt from scratch on every onClear/reconnect (own live checks via
-- onLocationChecked, plus a resync over Archipelago.CheckedLocations for anything
-- already checked in a previous session - see onClear).
local progress_checked_counts = { cups = 0, time_trial = 0, missions = 0 }

local PROGRESS_CODE = {
    cups = "progress_cups",
    time_trial = "progress_time_trial",
    missions = "progress_missions",
}

local PROGRESS_REQUIRED_LIST_KEY = {
    cups = "required_cups_in_order",
    time_trial = "required_time_trials_in_order",
    missions = "required_missions_in_order",
}

local PROGRESS_REQUIRED_COUNT_KEY = {
    cups = "required_cup_win_count",
    time_trial = "required_time_trial_win_count",
    missions = "required_mission_win_count",
}

-- Cached from the most recent onClear - progress overlays need slot_data's *_win_count,
-- which onLocationChecked doesn't otherwise have access to.
local cached_slot_data = {}

local function set_progress_overlay(category)
    local code = PROGRESS_CODE[category]
    local obj = Tracker:FindObjectForCode(code)
    if obj == nil then
        return
    end
    obj.Active = true  -- always visible - it's a text carrier, not itself an unlock state

    local required_list = cached_slot_data[PROGRESS_REQUIRED_LIST_KEY[category]]
    if required_list == nil or required_list[1] == nil then
        obj:SetOverlay("0/0")  -- category not part of this seed's goal at all
        return
    end

    local target = cached_slot_data[PROGRESS_REQUIRED_COUNT_KEY[category]] or 0
    local have = progress_checked_counts[category]
    if have > target then
        have = target  -- don't display e.g. "9/3" - extra checks beyond the target don't matter
    end
    obj:SetOverlay(have .. "/" .. target)
end

local function update_all_progress_displays()
    set_progress_overlay("cups")
    set_progress_overlay("time_trial")
    set_progress_overlay("missions")
end

local function onItemReceived(index, item_id, item_name, player_number)
    if CUP_NAME_SET[item_name] then
        cup_unlocked[item_name] = true
        return
    end

    -- Character/Kart toggles, or a Time Trial/Mission unlock item (both now real,
    -- individually-named AP items - see worlds/mkds/items.py and ITEM_NAME_TO_CODE's own
    -- generation comment). The filler "Green Flag" and anything else unrecognized just
    -- does nothing.
    local code = ITEM_NAME_TO_CODE[item_name]
    if code == nil then
        return
    end
    local obj = Tracker:FindObjectForCode(code)
    if obj == nil then
        return
    end

    if PROGRESSIVE_ITEM_CODES[code] then
        -- Never downgrade - a location-checked event could in principle arrive before
        -- its item-received counterpart on a slow/reordered connection, and receiving
        -- the unlock item afterward shouldn't un-complete it.
        if obj.CurrentStage < 1 then
            obj.CurrentStage = 1
        end
    else
        obj.Active = true
    end
end

local function mark_section_checked(location, section_name)
    local address = "@" .. location .. "/" .. section_name
    local obj = Tracker:FindObjectForCode(address)
    if obj ~= nil then
        obj.AvailableChestCount = 0
    end
end

local function mark_section_unchecked(location, section_name)
    local address = "@" .. location .. "/" .. section_name
    local obj = Tracker:FindObjectForCode(address)
    if obj ~= nil then
        obj.AvailableChestCount = 1  -- every section here has item_count 1 (its default)
    end
end

local function set_item_stage_checked(code, stage)
    local obj = Tracker:FindObjectForCode(code)
    if obj ~= nil and obj.CurrentStage < stage then
        obj.CurrentStage = stage
    end
end

local function onLocationChecked(location_id, location_name)
    local section_entry = LOCATION_NAME_TO_SECTION[location_name]
    if section_entry ~= nil then
        mark_section_checked(section_entry.location, section_entry.section)
    end
    local stage_entry = LOCATION_NAME_TO_ITEM_STAGE[location_name]
    if stage_entry ~= nil then
        set_item_stage_checked(stage_entry.code, stage_entry.stage)
    end

    -- Only top-tier locations (cup "- Win", track "- Staff Ghost Beaten", mission
    -- "- Clear") appear in this table (see generate_pack.py) - Silver/Bronze/race
    -- placements never bump a progress counter, matching what worlds/mkds/rules.py's
    -- completion_condition and client.py's _check_goal_complete actually count.
    local category = LOCATION_NAME_TO_PROGRESS_CATEGORY[location_name]
    if category ~= nil then
        progress_checked_counts[category] = progress_checked_counts[category] + 1
        update_all_progress_displays()
    end
end

local function activate_free_entry(slot_data, list_name)
    -- Position 0 of character_unlock_order/kart_unlock_order is free per-seed and never
    -- generates its own AP item event (see worlds/mkds/rules.py) - Characters/Karts are
    -- the only remaining category using this specific mechanism (Cups' own free
    -- bootstrap is handled directly in onClear below via cup_unlocked, since it isn't an
    -- items.json-backed object).
    local list = slot_data[list_name]
    if list == nil or list[1] == nil then
        return  -- category not active this seed (empty list), or slot_data not ready yet
    end
    local code = ITEM_NAME_TO_CODE[list[1]]
    if code == nil then
        return
    end
    local obj = Tracker:FindObjectForCode(code)
    if obj ~= nil then
        obj.Active = true
    end
end

local function activate_bootstrap_progressive(slot_data, key_name)
    -- Time Trial/Mission's own single random bootstrap entry (slot_data.time_trial_
    -- bootstrap/mission_bootstrap - a bare item name, NOT a list[0] like
    -- character_unlock_order/kart_unlock_order use just below) never generates its own
    -- AP item event - see worlds/mkds/rules.py's choose_category_bootstrap. Mirrors
    -- cup_bootstrap's own direct handling below, just advancing an items.json
    -- progressive item's stage instead of the Lua-only cup_unlocked table.
    local name = slot_data[key_name]
    if name == nil then
        return
    end
    local code = ITEM_NAME_TO_CODE[name]
    if code == nil then
        return
    end
    local obj = Tracker:FindObjectForCode(code)
    if obj ~= nil and obj.CurrentStage < 1 then
        obj.CurrentStage = 1
    end
end

local function onClear(slot_data)
    -- Called on (re)connect - reset every tracked object back to its locked/unchecked/
    -- inactive state before AP replays items_received (which re-fires onItemReceived for
    -- each), so a reconnect doesn't leave stale state from a previous session/seed on
    -- screen.
    progress_checked_counts = { cups = 0, time_trial = 0, missions = 0 }

    cup_unlocked = {}

    for _, code in pairs(ITEM_NAME_TO_CODE) do
        if not PROGRESSIVE_ITEM_CODES[code] then
            local obj = Tracker:FindObjectForCode(code)
            if obj ~= nil then
                obj.Active = false
            end
        end
    end

    for _, entry in pairs(LOCATION_NAME_TO_SECTION) do
        mark_section_unchecked(entry.location, entry.section)
    end

    -- Resets every Time Trial/Mission progressive item back to stage 0 (locked) - covers
    -- every such item since LOCATION_NAME_TO_ITEM_STAGE has exactly one entry per track/
    -- mission (its completion location), same roster as PROGRESSIVE_ITEM_CODES.
    for _, entry in pairs(LOCATION_NAME_TO_ITEM_STAGE) do
        local obj = Tracker:FindObjectForCode(entry.code)
        if obj ~= nil then
            obj.CurrentStage = 0
        end
    end

    slot_data = slot_data or {}
    cached_slot_data = slot_data
    activate_free_entry(slot_data, "character_unlock_order")
    activate_free_entry(slot_data, "kart_unlock_order")
    activate_bootstrap_progressive(slot_data, "time_trial_bootstrap")
    activate_bootstrap_progressive(slot_data, "mission_bootstrap")

    if slot_data.cup_bootstrap ~= nil then
        cup_unlocked[slot_data.cup_bootstrap] = true
    end

    -- Resync already-CHECKED locations after a reconnect. AddItemHandler's own
    -- replay-on-connect already covers Character/Kart items and received Cup unlock
    -- items (AP replays items_received automatically) - nothing replays past location
    -- checks the same way, so without this, every already-won cup/track
    -- placement/beaten ghost/cleared mission would incorrectly show as unchecked until
    -- re-completed (which can't happen, a location can only be checked once), and
    -- progress_checked_counts would incorrectly start back at 0 every reconnect.
    local checked = Archipelago.CheckedLocations
    if checked ~= nil then
        for _, location_id in ipairs(checked) do
            local section_entry = LOCATION_ID_TO_SECTION[location_id]
            if section_entry ~= nil then
                mark_section_checked(section_entry.location, section_entry.section)
            end
            local stage_entry = LOCATION_ID_TO_ITEM_STAGE[location_id]
            if stage_entry ~= nil then
                set_item_stage_checked(stage_entry.code, stage_entry.stage)
            end
            local category = LOCATION_ID_TO_PROGRESS_CATEGORY[location_id]
            if category ~= nil then
                progress_checked_counts[category] = progress_checked_counts[category] + 1
            end
        end
    end

    -- Must run last - depends on cached_slot_data and progress_checked_counts already
    -- being fully rebuilt above.
    update_all_progress_displays()
end

Archipelago:AddItemHandler("MKDS Item Tracker", onItemReceived)
Archipelago:AddLocationHandler("MKDS Location Tracker", onLocationChecked)
Archipelago:AddClearHandler("MKDS Item Tracker Reset", onClear)
