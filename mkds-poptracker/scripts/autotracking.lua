-- autotracking.lua
--
-- Archipelago autotracking for the MKDS PopTracker pack. Tracks two independent signals
-- per sequenced category (Characters/Karts are simple two-state toggles with no second
-- signal - see items/items.json):
--   1. UNLOCKED - an item was received (AddItemHandler), or this is the seed's free
--      position-0 entry for that category (only known via slot_data on connect/clear -
--      position 0 never generates its own AP item event, see onClear below).
--   2. COMPLETED - the corresponding location was checked (AddLocationHandler).
-- Cups/Tracks/Missions use "progressive" items with 3 explicit stages (0 locked, 1
-- unlocked-green, 2 unlocked-completed-grey) driven directly by setting .CurrentStage
-- from this script - NOT by simulated clicks, and NOT layered on top of a toggle-like
-- .Active flag, since that would leave "was this item ever received at all vs is it
-- just sitting at its lowest stage" ambiguous. This needs .CurrentStage to be directly
-- Lua-settable, confirmed against PopTracker's real docs (github.com/black-sliver/
-- PopTracker/blob/master/doc/PACKS.md, checked 2026-08-05) rather than guessed - this
-- project's established discipline after getting this pack's schema wrong once already
-- (see NOTES.md).
--
-- Written against PopTracker's documented Archipelago autotracking API
-- (github.com/black-sliver/PopTracker/blob/master/doc/AUTOTRACKING.md, checked
-- 2026-08-05): AddItemHandler's callback is (index, item_id, item_name, player_number);
-- AddLocationHandler's is (location_id, location_name); AddClearHandler's is
-- (slot_data); Archipelago.CheckedLocations is an array of already-checked location ids,
-- nil on PopTracker installs older than 0.25.2 (see manifest.json's
-- min_poptracker_version). NOT YET TESTED against a real PopTracker install - flagging
-- honestly rather than claiming this works untested, matching this project's established
-- practice (see NOTES.md) - the API shapes are taken directly from PopTracker's own
-- current docs, not guessed, but this specific script/pack hasn't been run in a live
-- PopTracker session yet.

ScriptHost:LoadScript("scripts/item_name_to_code.lua")
ScriptHost:LoadScript("scripts/location_name_to_code.lua")
ScriptHost:LoadScript("scripts/location_id_to_code.lua")
ScriptHost:LoadScript("scripts/progressive_item_codes.lua")

local function onItemReceived(index, item_id, item_name, player_number)
    -- item_name matches the AP item name exactly (e.g. "Daisy", "Mushroom Cup",
    -- "Figure-8 Circuit", or a mission's bare "Level N Mission M - <objective>" name,
    -- with NO "- Clear"/"- Staff Ghost Beaten" suffix - that suffix only exists on the
    -- corresponding LOCATION name, see location_name_to_code.lua) - not a tracked item
    -- (e.g. the filler "Green Flag") just does nothing.
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

local function onLocationChecked(location_id, location_name)
    local code = LOCATION_NAME_TO_CODE[location_name]
    if code == nil then
        return  -- not a tracked location (e.g. a "- 1st Place" individual race win -
        -- this pack only tracks cup/track/mission UNLOCK+COMPLETE state, not every
        -- possible check)
    end

    local obj = Tracker:FindObjectForCode(code)
    if obj ~= nil then
        obj.CurrentStage = 2
    end
end

local function activate_free_entry(slot_data, list_name, is_progressive)
    -- Position 0 of a sequenced category (character_unlock_order/required_cups_in_order/
    -- required_time_trials_in_order/required_missions_in_order) is free per-seed and
    -- never generates its own AP item event (see worlds/mkds/rules.py's
    -- _sequence_access_rule) - mark it directly here, the one place slot_data is
    -- available. Without this, the seed's free starting character/cup/track/mission
    -- would incorrectly show locked forever.
    local list = slot_data[list_name]
    if list == nil or list[1] == nil then
        return  -- category not active this seed (empty list), or slot_data not ready yet
    end

    local code = ITEM_NAME_TO_CODE[list[1]]
    if code == nil then
        return
    end

    local obj = Tracker:FindObjectForCode(code)
    if obj == nil then
        return
    end

    if is_progressive then
        obj.CurrentStage = 1
    else
        obj.Active = true
    end
end

local function onClear(slot_data)
    -- Called on (re)connect - reset every tracked item back to its locked/inactive state
    -- before AP replays items_received (which re-fires onItemReceived for each), so a
    -- reconnect doesn't leave stale state from a previous session/seed on screen.
    for _, code in pairs(ITEM_NAME_TO_CODE) do
        local obj = Tracker:FindObjectForCode(code)
        if obj ~= nil then
            if PROGRESSIVE_ITEM_CODES[code] then
                obj.CurrentStage = 0
            else
                obj.Active = false
            end
        end
    end

    slot_data = slot_data or {}
    activate_free_entry(slot_data, "character_unlock_order", false)
    activate_free_entry(slot_data, "kart_unlock_order", false)
    activate_free_entry(slot_data, "required_cups_in_order", true)
    activate_free_entry(slot_data, "required_time_trials_in_order", true)
    activate_free_entry(slot_data, "required_missions_in_order", true)

    -- Resync already-COMPLETED locations (green -> grey) after a reconnect.
    -- AddItemHandler's own replay-on-connect already covers the UNLOCK half (AP replays
    -- items_received automatically) - nothing replays past location checks the same way,
    -- so without this, every already-won cup/beaten ghost/cleared mission would
    -- incorrectly show green again until re-completed, which can't happen (a location
    -- can only be checked once).
    local checked = Archipelago.CheckedLocations
    if checked ~= nil then
        for _, location_id in ipairs(checked) do
            local code = LOCATION_ID_TO_CODE[location_id]
            if code ~= nil then
                local obj = Tracker:FindObjectForCode(code)
                if obj ~= nil then
                    obj.CurrentStage = 2
                end
            end
        end
    end
end

Archipelago:AddItemHandler("MKDS Item Tracker", onItemReceived)
Archipelago:AddLocationHandler("MKDS Location Tracker", onLocationChecked)
Archipelago:AddClearHandler("MKDS Item Tracker Reset", onClear)
