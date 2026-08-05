-- probe.lua
--
-- Diagnostic tool for mapping Mario Kart DS's RAM layout. NOT part of the shipped
-- world - this only exists to help find real addresses during development.
--
-- Trigger files polled every frame:
--   trigger.txt         -> read/snapshot request (label as content). Dumps REGIONS.
--   write_trigger.txt    -> write request. One line: "<hex address> <hex byte> ..."
--   macro_trigger.txt     -> scripted input/screenshot sequence, one command per line:
--       PRESS <button> <hold_frames> <wait_frames>   e.g. "PRESS A 2 20"
--       WAIT <frames>
--       SCREENSHOT <label>
--       OPENROM <path>   loads a different ROM file (path may contain spaces - takes the
--         rest of the line verbatim). For switching regions without manual GUI steps.
--       READAT <hex_addr> <hex_len> <out_label> [domain]   one-shot read of an arbitrary
--         address, dumped straight to a file - for verifying specific known offsets/
--         pointers. Optional domain (spaces as '_', e.g. "ROM") defaults to "ARM9 System
--         Bus" - use this to read the raw cartridge ("ROM" domain) instead of live
--         mapped memory, e.g. for the cartridge header, which does NOT reliably appear
--         at a fixed low address on "ARM9 System Bus" (that region can be shadowed by
--         Instruction TCM remapping - confirmed 2026-08-04, see NOTES.md).
--       FINDBYTES <hex_addr> <hex_len> <hex_pattern> <out_label>   raw byte-pattern search
--         across a region (no wildcards) - writes every matching address to a file. For
--         finding a struct by an expected field VALUE (e.g. a known character id) rather
--         than by watching it change, unlike NARROWSTART/TOGGLE below.
--       SCANSTART <hex_addr> <hex_len> <slot_label>   store a region in memory (not a file)
--       SCANDIFF <slot_label_a> <slot_label_b> <out_label>   diff two stored scans, write
--         ONLY the changed offsets (addr, old byte, new byte) to a file - much smaller/
--         more useful than raw hex dumps for finding live game-state addresses.
--       NARROWSTART <hex_addr> <hex_len> <label>   begin an iterative narrowing search
--         (replicates RAM Search's repeated "changed value" filtering). Call once while
--         the game is in "state A".
--       NARROWTOGGLE <label> <A|B>   call after switching the game to state A or state
--         B. The first "B" call fixes the reference value for state B and narrows to
--         "changed from A"; every call after that narrows further to addresses whose
--         CURRENT value still matches the remembered reference for that state - so the
--         candidate set converges on addresses that consistently flip between exactly
--         two values in sync with the toggle, not just anything that happened to change.
--       NARROWDUMP <label> <out_label>   write the surviving candidates (address, value
--         at A, value at B) to a file.
--       WATCHWRITE <hex_addr> <label>   registers a live hardware watchpoint (via
--         event.on_bus_write) on a single address - every time ANYTHING in the game
--         writes to it, records the current frame, PC (ARM9 r15), LR (ARM9 r14, the
--         caller's return address), and the value written. PERSISTS across macro calls/
--         frames until WATCHCLEAR - this is for catching rare, hard-to-predict events
--         (e.g. "does normal gameplay ever write here without any external write?"),
--         unlike everything else in this file which is a one-shot poll.
--       WATCHREAD <hex_addr> <label>   same as WATCHWRITE but for reads (event.on_bus_
--         read) - use to find what CODE consults an address, even when you don't have a
--         function symbol to search for calls to (e.g. an inlined bit-test, which no
--         "find calls to X" search could ever catch).
--       WATCHEXEC <hex_addr> <label>   watches whether a specific CODE address is ever
--         reached (event.on_bus_exec) - "ANY" is NOT supported here (always requires one
--         specific address - see the crash-safety note above). Use to settle whether a
--         SPECIFIC candidate function address (e.g. from a symbol table you're not sure
--         is trustworthy) is actually ever executed during real gameplay, independent of
--         whether static disassembly at that address looks coherent.
--       WATCHDUMP <label> <out_label>   writes every hit recorded for `label` so far to
--         a file (one line per hit) - does NOT clear/stop the watch, safe to call
--         repeatedly to check progress.
--       WATCHCLEAR <label>   unregisters the watchpoint and discards its recorded hits.
--     NOTE: hardware watchpoints need the core's IDebuggable.MemoryCallbacks - confirmed
--     supported for melonDS (EnableJIT must be OFF in NDS core sync settings, or
--     registration silently fails - Config > ... core-specific NDS settings if WATCHWRITE/
--     WATCHREAD never produce any hits even when you know the address must be touched).
--     Button names must match what this core reports - see "known buttons" in the log
--     at startup. Commands execute in order, one macro file per trigger.
--
-- Usage: Tools > Lua Console > Open Script (or Reload), pick this file, then play
-- normally. Someone else (or another process) writes to the trigger files.

local BASE = "F:/Mario Kart DS AP/reference/ram_probe/"
local TRIGGER = BASE .. "trigger.txt"
local WRITE_TRIGGER = BASE .. "write_trigger.txt"
local MACRO_TRIGGER = BASE .. "macro_trigger.txt"
local OUTDIR = BASE .. "snapshots/"
local SHOTDIR = BASE .. "screenshots/"
local LOGFILE = BASE .. "probe_log.txt"

local REGIONS = {
    { 0x023CE000, 0x800, "unlock_struct_candidate" },
}

local scan_slots = {}  -- label -> {addr=.., bytes={...}}
local narrow_slots = {}  -- label -> {addr=.., len=.., candidates={[offset]=true}, ref_a={...}, ref_b={...}}
local watch_hits = {}  -- label -> array of hit-description strings
local watch_ids = {}  -- label -> event guid string (for WATCHCLEAR)

local DOMAIN = "ARM9 System Bus"

local function log(msg)
    local f = io.open(LOGFILE, "a")
    if f then f:write(msg .. "\n") f:close() end
end

local function file_exists(path)
    local f = io.open(path, "r")
    if f then f:close() return true end
    return false
end

local function read_file(path)
    local f = io.open(path, "r")
    if not f then return nil end
    local content = f:read("*a")
    f:close()
    return content
end

local function trim(s)
    return (s:gsub("^%s+", ""):gsub("%s+$", ""))
end

-- tonumber(s, 16) does NOT accept a "0x" prefix once a base is given explicitly
-- (that auto-detection only happens when base is omitted) - strip it first so
-- macro/trigger commands work whether or not the caller included "0x". An
-- unstripped "0x..." string makes tonumber return nil, which previously fed
-- nil straight into memory.read_bytes_as_array and killed the script's frame
-- loop with an uncaught error (confirmed 2026-08-04).
local function parse_hex(s)
    if s == nil then return nil end
    s = s:gsub("^0[xX]", "")
    return tonumber(s, 16)
end

-- startup diagnostics
local ok_list, domain_list = pcall(function() return memory.getmemorydomainlist() end)
if ok_list then
    log("=== available memory domains ===")
    for i, d in ipairs(domain_list) do log(i .. ": " .. tostring(d)) end
else
    log("memory.getmemorydomainlist() failed: " .. tostring(domain_list))
end

local ok_pad, pad = pcall(function() return joypad.get() end)
if ok_pad then
    log("=== known joypad buttons (joypad.get()) ===")
    for k, v in pairs(pad) do log(tostring(k) .. " = " .. tostring(v)) end
else
    log("joypad.get() failed: " .. tostring(pad))
end

log("=== probe ready (read + write + macro) ===")

-- macro execution state
local macro_queue = {}
local macro_cursor = 0
local macro_state = nil  -- {type="press", button=.., hold=.., wait=..} or {type="wait", frames=..}

local function load_macro()
    if not file_exists(MACRO_TRIGGER) then return end
    local raw = read_file(MACRO_TRIGGER)
    os.remove(MACRO_TRIGGER)
    macro_queue = {}
    macro_cursor = 0
    macro_state = nil
    if not raw then return end
    for line in raw:gmatch("[^\r\n]+") do
        local tokens = {}
        for w in line:gmatch("%S+") do table.insert(tokens, w) end
        if #tokens > 0 then table.insert(macro_queue, tokens) end
    end
    log(string.format("[macro] loaded %d command(s)", #macro_queue))
end

local function advance_macro()
    if macro_state == nil then
        if macro_cursor >= #macro_queue then return end  -- nothing queued, don't spin
        macro_cursor = macro_cursor + 1
        local cmd = macro_queue[macro_cursor]
        if cmd == nil then return end  -- queue empty/finished

        local op = cmd[1]:upper()
        if op == "PRESS" then
            macro_state = { type = "press", button = cmd[2], hold = tonumber(cmd[3]) or 1, wait = tonumber(cmd[4]) or 0 }
            log(string.format("[macro] PRESS %s hold=%d wait=%d", macro_state.button, macro_state.hold, macro_state.wait))
        elseif op == "WAIT" then
            macro_state = { type = "wait", frames = tonumber(cmd[2]) or 1 }
            log(string.format("[macro] WAIT %d", macro_state.frames))
        elseif op == "SCREENSHOT" then
            local label = (cmd[2] or "shot"):gsub("[^%w_%-]", "_")
            local path = SHOTDIR .. label .. ".png"
            local ok, err = pcall(function() client.screenshot(path) end)
            log(string.format("[macro] SCREENSHOT '%s' -> %s (%s)", label, path, ok and "ok" or tostring(err)))
            macro_state = nil  -- instantaneous, move on next frame
        elseif op == "REBOOT" then
            local ok, err = pcall(function() client.reboot_core() end)
            log(string.format("[macro] REBOOT (%s)", ok and "ok" or tostring(err)))
            macro_state = nil
        elseif op == "OPENROM" then
            -- Path may contain spaces - tokens[2:] rejoined with single spaces
            -- reconstructs it (loses any double-spaces, not a concern for known paths).
            local path = table.concat(cmd, " ", 2)
            local ok, err = pcall(function() client.openrom(path) end)
            log(string.format("[macro] OPENROM '%s' (%s)", path, ok and "ok" or tostring(err)))
            macro_state = nil
        elseif op == "TOUCH" then
            macro_state = {
                type = "touch",
                x = tonumber(cmd[2]) or 0,
                y = tonumber(cmd[3]) or 0,
                hold = tonumber(cmd[4]) or 5,
                wait = tonumber(cmd[5]) or 30,
            }
            log(string.format("[macro] TOUCH x=%d y=%d hold=%d wait=%d", macro_state.x, macro_state.y, macro_state.hold, macro_state.wait))
        elseif op == "READAT" then
            -- One-shot read of an arbitrary address, dumped straight to a file (unlike
            -- SCANSTART, which stores in memory for later diffing). For verifying
            -- specific known offsets/pointers, e.g. from external documentation.
            -- Optional 5th arg: domain name (spaces replaced with '_', e.g. "ROM" or
            -- "Instruction_TCM") - defaults to DOMAIN ("ARM9 System Bus") if omitted.
            local addr = parse_hex(cmd[2])
            local len = parse_hex(cmd[3])
            local out_label = cmd[4] or "readat"
            local read_domain = cmd[5] and cmd[5]:gsub("_", " ") or DOMAIN
            local ok, bytes = pcall(function() return memory.read_bytes_as_array(addr, len, read_domain) end)
            if ok then
                local path = OUTDIR .. out_label:gsub("[^%w_%-]", "_") .. ".txt"
                local f = io.open(path, "w")
                if f then
                    f:write(string.format("addr=0x%08X len=0x%X\n", addr, len))
                    for i, b in ipairs(bytes) do
                        f:write(string.format("%02X", b))
                        if i % 16 == 0 then f:write("\n") else f:write(" ") end
                    end
                    f:write("\n")
                    f:close()
                    log(string.format("[macro] READAT 0x%08X len=0x%X domain='%s' -> %s", addr, len, read_domain, path))
                end
            else
                log(string.format("[macro] READAT FAILED 0x%08X domain='%s': %s", addr, read_domain, tostring(bytes)))
            end
            macro_state = nil
        elseif op == "FINDBYTES" then
            -- Raw byte-pattern search across a region - unlike NARROWSTART (which needs
            -- state A/B toggling), this just finds every offset where a known, fixed byte
            -- sequence appears right now. For hunting a struct by an expected field VALUE
            -- (e.g. a known character_id) rather than by watching something change.
            local addr = parse_hex(cmd[2])
            local len = parse_hex(cmd[3])
            local pattern_hex = cmd[4] or ""
            local out_label = cmd[5] or "findbytes"
            local pattern = {}
            for i = 1, #pattern_hex, 2 do
                pattern[#pattern + 1] = tonumber(pattern_hex:sub(i, i + 1), 16)
            end
            local ok, bytes = pcall(function() return memory.read_bytes_as_array(addr, len, DOMAIN) end)
            if ok and #pattern > 0 then
                local path = OUTDIR .. out_label:gsub("[^%w_%-]", "_") .. ".txt"
                local f = io.open(path, "w")
                local matches = 0
                if f then
                    f:write(string.format("base=0x%08X len=0x%X pattern=%s\n", addr, len, pattern_hex))
                    for i = 1, #bytes - #pattern + 1 do
                        local match = true
                        for j = 1, #pattern do
                            if bytes[i + j - 1] ~= pattern[j] then match = false break end
                        end
                        if match then
                            matches = matches + 1
                            f:write(string.format("0x%08X\n", addr + i - 1))
                        end
                    end
                    f:close()
                end
                log(string.format("[macro] FINDBYTES 0x%08X len=0x%X pattern=%s -> %s (%d matches)", addr, len, pattern_hex, path, matches))
            else
                log(string.format("[macro] FINDBYTES FAILED 0x%08X: %s", addr, tostring(bytes)))
            end
            macro_state = nil
        elseif op == "SCANSTART" then
            local addr = parse_hex(cmd[2])
            local len = parse_hex(cmd[3])
            local slot = cmd[4] or "scan"
            local ok, bytes = pcall(function() return memory.read_bytes_as_array(addr, len, DOMAIN) end)
            if ok then
                scan_slots[slot] = { addr = addr, bytes = bytes }
                log(string.format("[macro] SCANSTART '%s' 0x%08X len=0x%X stored (%d bytes)", slot, addr, len, #bytes))
            else
                log(string.format("[macro] SCANSTART FAILED 0x%08X: %s", addr, tostring(bytes)))
            end
            macro_state = nil
        elseif op == "SCANDIFF" then
            local slot_a, slot_b, out_label = cmd[2], cmd[3], cmd[4] or "scandiff"
            local a, b = scan_slots[slot_a], scan_slots[slot_b]
            if a == nil or b == nil then
                log(string.format("[macro] SCANDIFF missing slot(s): a=%s b=%s", tostring(a), tostring(b)))
            elseif a.addr ~= b.addr or #a.bytes ~= #b.bytes then
                log("[macro] SCANDIFF slots don't match in addr/length")
            else
                local path = OUTDIR .. out_label:gsub("[^%w_%-]", "_") .. ".txt"
                local f = io.open(path, "w")
                local diffcount = 0
                if f then
                    f:write(string.format("base=0x%08X len=0x%X (only changed bytes shown)\n", a.addr, #a.bytes))
                    for i = 1, #a.bytes do
                        if a.bytes[i] ~= b.bytes[i] then
                            diffcount = diffcount + 1
                            f:write(string.format("0x%08X: %02X -> %02X\n", a.addr + i - 1, a.bytes[i], b.bytes[i]))
                        end
                    end
                    f:close()
                end
                log(string.format("[macro] SCANDIFF '%s' vs '%s' -> %s (%d changed bytes)", slot_a, slot_b, path, diffcount))
            end
            macro_state = nil
        elseif op == "NARROWSTART" then
            -- Begin an iterative narrowing search (replicates RAM Search's repeated
            -- "changed value" filtering). Call once at the FIRST state (state A).
            local addr = parse_hex(cmd[2])
            local len = parse_hex(cmd[3])
            local label = cmd[4]
            local ok, bytes = pcall(function() return memory.read_bytes_as_array(addr, len, DOMAIN) end)
            if ok then
                local candidates = {}
                for i = 1, #bytes do candidates[i] = true end
                narrow_slots[label] = { addr = addr, len = len, candidates = candidates, ref_a = bytes, ref_b = nil, count = #bytes }
                log(string.format("[macro] NARROWSTART '%s' 0x%08X len=0x%X candidates=%d", label, addr, len, #bytes))
            else
                log("[macro] NARROWSTART FAILED: " .. tostring(bytes))
            end
            macro_state = nil
        elseif op == "NARROWTOGGLE" then
            -- Call after switching to state A or state B. First call with "B" fixes the
            -- reference value for state B and narrows to "changed from A". Every call
            -- after that narrows the candidate set to addresses whose CURRENT value
            -- still matches the remembered reference for that state - much stronger
            -- than plain "changed", since it requires consistently flipping between
            -- exactly the same two values, not just moving.
            local label = cmd[2]
            local which = (cmd[3] or "A"):upper()
            local slot = narrow_slots[label]
            if slot == nil then
                log("[macro] NARROWTOGGLE: no such label " .. tostring(label))
            else
                local ok, bytes = pcall(function() return memory.read_bytes_as_array(slot.addr, slot.len, DOMAIN) end)
                if ok then
                    if which == "B" and slot.ref_b == nil then
                        slot.ref_b = bytes
                        local new_candidates, kept = {}, 0
                        for i, _ in pairs(slot.candidates) do
                            if bytes[i] ~= slot.ref_a[i] then
                                new_candidates[i] = true
                                kept = kept + 1
                            end
                        end
                        slot.candidates, slot.count = new_candidates, kept
                        log(string.format("[macro] NARROWTOGGLE '%s' B (establishing ref_b) -> %d candidates", label, kept))
                    else
                        local ref = (which == "A") and slot.ref_a or slot.ref_b
                        if ref == nil then
                            log(string.format("[macro] NARROWTOGGLE '%s' %s: reference not established yet", label, which))
                        else
                            local new_candidates, kept = {}, 0
                            for i, _ in pairs(slot.candidates) do
                                if bytes[i] == ref[i] then
                                    new_candidates[i] = true
                                    kept = kept + 1
                                end
                            end
                            slot.candidates, slot.count = new_candidates, kept
                            log(string.format("[macro] NARROWTOGGLE '%s' %s -> %d candidates", label, which, kept))
                        end
                    end
                else
                    log("[macro] NARROWTOGGLE read failed: " .. tostring(bytes))
                end
            end
            macro_state = nil
        elseif op == "NARROWDUMP" then
            local label = cmd[2]
            local out_label = cmd[3] or "narrowdump"
            local slot = narrow_slots[label]
            if slot == nil then
                log("[macro] NARROWDUMP: no such label " .. tostring(label))
            else
                local path = OUTDIR .. out_label:gsub("[^%w_%-]", "_") .. ".txt"
                local f = io.open(path, "w")
                if f then
                    f:write(string.format("base=0x%08X len=0x%X candidates=%d\n", slot.addr, slot.len, slot.count))
                    local offsets = {}
                    for i, _ in pairs(slot.candidates) do table.insert(offsets, i) end
                    table.sort(offsets)
                    for _, i in ipairs(offsets) do
                        local a_val = slot.ref_a and slot.ref_a[i] or 0
                        local b_val = slot.ref_b and slot.ref_b[i] or 0
                        f:write(string.format("0x%08X: A=%02X B=%02X\n", slot.addr + i - 1, a_val, b_val))
                    end
                    f:close()
                    log(string.format("[macro] NARROWDUMP '%s' -> %s (%d candidates)", label, path, slot.count))
                end
            end
            macro_state = nil
        elseif op == "WATCHWRITE" or op == "WATCHREAD" or op == "WATCHEXEC" then
            -- Live hardware watchpoint via event.on_bus_write/on_bus_read/on_bus_exec -
            -- persists across frames/macro calls (unlike everything else here) until
            -- WATCHCLEAR. Records frame/addr/PC/LR/value for every hit into
            -- watch_hits[label]; use WATCHDUMP to inspect progress at any time without
            -- stopping the watch.
            -- Address may be "ANY" (case-insensitive) for a wildcard watch (fires on
            -- EVERY access in scope - CPU-intensive, capped at WATCH_HIT_CAP hits and
            -- auto-clears itself once hit, as a safety net against runaway memory use
            -- if a macro forgets to WATCHCLEAR promptly). NOT supported for WATCHEXEC
            -- specifically (deliberately - a wildcard exec watch fires on every single
            -- instruction fetched, which would be even worse than the wildcard READ
            -- watch that hard-crashed BizHawk once already - see NOTES.md. WATCHEXEC
            -- always requires one specific address.
            local is_wildcard = op ~= "WATCHEXEC" and cmd[2] and cmd[2]:upper() == "ANY"
            local addr
            if not is_wildcard then
                addr = parse_hex(cmd[2])
            end
            local label = cmd[3] or "watch"
            if watch_ids[label] then
                log(string.format("[macro] %s '%s': already active, ignoring (WATCHCLEAR first to restart)", op, label))
            else
                watch_hits[label] = {}
                local register_fn = event.on_bus_read
                if op == "WATCHWRITE" then register_fn = event.on_bus_write end
                if op == "WATCHEXEC" then register_fn = event.on_bus_exec end
                local WATCH_HIT_CAP = 2000
                local ok, guid_or_err = pcall(function()
                    return register_fn(function(a, v, flags)
                        if #watch_hits[label] >= WATCH_HIT_CAP then
                            if watch_ids[label] then
                                event.unregisterbyid(watch_ids[label])
                                watch_ids[label] = nil
                            end
                            return
                        end
                        local pc_ok, pc = pcall(function() return emu.getregister("ARM9 r15") end)
                        local lr_ok, lr = pcall(function() return emu.getregister("ARM9 r14") end)
                        table.insert(watch_hits[label], string.format(
                            "frame=%d addr=0x%08X pc=0x%08X lr=0x%08X val=0x%08X",
                            frame, a or 0, pc_ok and pc or -1, lr_ok and lr or -1, v or 0))
                    end, addr, label, DOMAIN)
                end)
                local addr_str = addr and string.format("0x%08X", addr) or "ANY"
                if ok then
                    watch_ids[label] = guid_or_err
                    log(string.format("[macro] %s %s label='%s' registered (id=%s)", op, addr_str, label, tostring(guid_or_err)))
                else
                    log(string.format("[macro] %s %s label='%s' FAILED: %s (check EnableJIT is off in NDS core sync settings)", op, addr_str, label, tostring(guid_or_err)))
                end
            end
            macro_state = nil
        elseif op == "WATCHDUMP" then
            local label = cmd[2]
            local out_label = cmd[3] or "watchdump"
            local hits = watch_hits[label] or {}
            local path = OUTDIR .. out_label:gsub("[^%w_%-]", "_") .. ".txt"
            local f = io.open(path, "w")
            if f then
                f:write(string.format("watch '%s': %d hit(s) so far (still active: %s)\n", label, #hits, tostring(watch_ids[label] ~= nil)))
                for _, line in ipairs(hits) do
                    f:write(line .. "\n")
                end
                f:close()
            end
            log(string.format("[macro] WATCHDUMP '%s' -> %s (%d hits)", label, path, #hits))
            macro_state = nil
        elseif op == "WATCHCLEAR" then
            local label = cmd[2]
            if watch_ids[label] then
                event.unregisterbyid(watch_ids[label])
                watch_ids[label] = nil
                local count = watch_hits[label] and #watch_hits[label] or 0
                watch_hits[label] = nil
                log(string.format("[macro] WATCHCLEAR '%s' (%d hits discarded)", label, count))
            else
                log(string.format("[macro] WATCHCLEAR '%s': not active", label))
            end
            macro_state = nil
        elseif op == "SCOPES" then
            -- Lists what event.availableScopes() reports for this core - cheap,
            -- read-only, safe diagnostic (no risk of a wildcard-style hang).
            local ok, scopes = pcall(function() return event.availableScopes() end)
            if ok then
                local parts = {}
                for _, s in ipairs(scopes) do table.insert(parts, tostring(s)) end
                log("[macro] SCOPES: " .. table.concat(parts, ", "))
            else
                log("[macro] SCOPES FAILED: " .. tostring(scopes))
            end
            macro_state = nil
        else
            log("[macro] unknown command: " .. cmd[1])
            macro_state = nil
        end
        return
    end

    if macro_state.type == "press" then
        if macro_state.hold > 0 then
            local ok, err = pcall(function() joypad.set({ [macro_state.button] = true }) end)
            if not ok then log("[macro] joypad.set failed: " .. tostring(err)) end
            macro_state.hold = macro_state.hold - 1
        elseif macro_state.wait > 0 then
            macro_state.wait = macro_state.wait - 1
        else
            macro_state = nil
        end
    elseif macro_state.type == "wait" then
        macro_state.frames = macro_state.frames - 1
        if macro_state.frames <= 0 then macro_state = nil end
    elseif macro_state.type == "touch" then
        if macro_state.hold > 0 then
            local ok, err = pcall(function()
                joypad.set({ Touch = true, ["Touch X"] = macro_state.x, ["Touch Y"] = macro_state.y })
            end)
            if not ok then log("[macro] touch failed: " .. tostring(err)) end
            macro_state.hold = macro_state.hold - 1
        elseif macro_state.wait > 0 then
            macro_state.wait = macro_state.wait - 1
        else
            macro_state = nil
        end
    end
end

local frame = 0
while true do
    frame = frame + 1

    if file_exists(TRIGGER) then
        local raw = read_file(TRIGGER)
        local label = raw and trim(raw) or ""
        if label == "" then label = "frame" .. frame end
        label = label:gsub("[^%w_%-]", "_")

        for _, region in ipairs(REGIONS) do
            local addr, len, tag = region[1], region[2], region[3]
            local ok, bytes = pcall(function() return memory.read_bytes_as_array(addr, len, DOMAIN) end)
            if ok then
                local outpath = OUTDIR .. label .. "__" .. tag .. ".txt"
                local f = io.open(outpath, "w")
                if f then
                    f:write(string.format("label=%s frame=%d domain=%s addr=0x%08X len=%d\n", label, frame, DOMAIN, addr, len))
                    for i, b in ipairs(bytes) do
                        f:write(string.format("%02X", b))
                        if i % 16 == 0 then f:write("\n") else f:write(" ") end
                    end
                    f:write("\n") f:close()
                    log(string.format("[frame %d] snapshot '%s' -> %s", frame, label, outpath))
                end
            else
                log(string.format("[frame %d] FAILED reading '%s': %s", frame, tag, tostring(bytes)))
            end
        end
        os.remove(TRIGGER)
    end

    if file_exists(WRITE_TRIGGER) then
        local raw = read_file(WRITE_TRIGGER)
        local line = raw and trim(raw) or ""
        if line ~= "" then
            local parts = {}
            for tok in line:gmatch("%S+") do table.insert(parts, tok) end
            if #parts >= 2 then
                local addr = parse_hex(parts[1])
                local bytes = {}
                for i = 2, #parts do table.insert(bytes, parse_hex(parts[i])) end
                local ok, err = pcall(function() memory.write_bytes_as_array(addr, bytes, DOMAIN) end)
                log(string.format("[frame %d] WRITE 0x%08X: %s (%s)", frame, addr, line, ok and "ok" or tostring(err)))
            end
        end
        os.remove(WRITE_TRIGGER)
    end

    load_macro()
    advance_macro()

    emu.frameadvance()
end
