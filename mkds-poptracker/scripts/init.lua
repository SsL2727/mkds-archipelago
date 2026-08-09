-- init.lua
--
-- Pack entry point - PopTracker loads this first (see doc/PACKS.md: "Everything a pack
-- provides is done through Lua, starting at scripts/init.lua"). Items/maps/locations/
-- layouts are NOT auto-discovered by folder convention - each file has to be explicitly
-- loaded here (confirmed against a real published pack - mario-kart-double-dash-ap's own
-- init.lua uses this exact same explicit-call pattern, one Tracker:Add* call per file).
--
-- Cups + Grand Prix placements are real PopTracker locations (locations/cups.json,
-- locations/grandPrixTracks.json). Time Trial + Missions moved back to items.json
-- progressive items (2026-08-06, per user direction after trying the location/map
-- version live) - see generate_pack.py's module docstring.

Tracker:AddItems("items/items.json")

Tracker:AddMaps("maps/maps.json")

Tracker:AddLocations("locations/cups.json")
Tracker:AddLocations("locations/grandPrixTracks.json")

Tracker:AddLayouts("layouts/layouts.json")

ScriptHost:LoadScript("scripts/autotracking.lua")
