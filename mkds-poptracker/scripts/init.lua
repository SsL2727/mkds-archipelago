-- init.lua
--
-- Pack entry point - PopTracker loads this first (see doc/PACKS.md: "Everything a pack
-- provides is done through Lua, starting at scripts/init.lua"). Items/layouts are NOT
-- auto-discovered by folder convention - they have to be explicitly loaded here.

Tracker:AddItems("items/items.json")
Tracker:AddLayouts("layouts/layouts.json")

ScriptHost:LoadScript("scripts/autotracking.lua")
