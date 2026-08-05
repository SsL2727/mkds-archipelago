# find_literal_refs.py
#
# Second-pass search for the character/cup-select unlock-check code, built after
# resilient_scan_for_calls() (mkds_disasm.py) found calls for only 2 of 9 known bits
# (Lightning Cup=12, Mirror=16) and turned up NOTHING for the baseline-content question
# (8 starter characters, base karts, 4 free cups) across the main ARM9 binary + all 4
# overlays. That search only finds explicit BL/BLX to named functions - it is BLIND to
# code that loads the flags word and does an INLINE bit-test (AND/TST + branch) without
# ever calling a function, which is a very plausible compiler output for a simple
# "if (flags & BIT) { ... }" check.
#
# Strategy: rather than searching for calls to a function, search for references to
# g_SaveDataHolder's own STATIC address (mkds-re symbol, EU 0x0217AA08 - a compile-time
# constant, unlike the heap-allocated UNLOCK_FLAGS_ADDRESS itself which can't appear
# literally in code). ARM/THUMB compilers load a global pointer's address via a
# PC-relative literal-pool load (LDR Rd, [PC, #imm]); the literal pool holding the raw
# 0x0217AA08 value sits a short distance AFTER the instruction that references it. So:
#   1. Find every 4-byte little-endian occurrence of 0x0217AA08 in the binary (candidate
#      literal-pool slots).
#   2. For each, scan BACKWARD (within the max PC-relative range: 4092 bytes for ARM,
#      1020 bytes for THUMB) for an LDR-literal instruction whose computed target
#      EXACTLY matches that slot's address.
#   3. For each confirmed reference, disassemble forward a short distance to inspect
#      what's done with the loaded pointer (dereference + offset access, further
#      indirection, bit-test, etc) - printed for manual review rather than auto-classified,
#      since distinguishing "the real unlock check" from "unrelated save-data code" (there
#      are MANY legitimate reasons to touch g_SaveDataHolder - saving, section-busy
#      checks, friend list, ghost data...) needs human judgement.
#
# Struct layout context (mkds-eu-types.h): g_SaveDataHolder is `SaveDataHolder *` - the
# struct itself is only 0x48 bytes and holds POINTERS to sub-sections (sv_header +0x0,
# sv_em +0x4, sv_gp(GrandPrix) +0x8, sv_tt(TimeTrial) +0xC, sv_mr(MissionRun) +0x10, ...)
# plus two suggestively-named trailing fields: unk_bits[4] at +0x30 and
# other_secret_bits[4] at +0x34. NOTES.md's "+0x70 from deref" hypothesis for
# UNLOCK_FLAGS_ADDRESS was never independently confirmed via a live pointer-value read
# (the watchpoint on g_SaveDataHolder's own address had zero hits all night) - it's
# geometrically odd too (0x70 is past the struct's documented 0x48-byte end, meaning
# either padding/adjacent-allocation weirdness or the hypothesis is simply wrong). Do NOT
# assume it's correct going in - this script surfaces raw reference sites so the actual
# offset used in real code can be read directly instead of guessed.

import struct

import capstone

from mkds_disasm import (
    ROM_PATH,
    load_rom,
    decompress_main_arm9,
    parse_overlay_table,
    extract_overlay,
)

G_SAVE_DATA_HOLDER_ADDR = 0x0217AA08

ARM_LITERAL_RANGE = 4092   # imm12 max (0xFFF), word-aligned
THUMB_LITERAL_RANGE = 1020  # imm8*4 max (0xFF * 4), word-aligned


def find_raw_occurrences(data: bytes, base: int, value: int) -> list[int]:
    """Every runtime address where the 4-byte little-endian `value` appears in `data`."""
    needle = struct.pack("<I", value)
    hits = []
    start = 0
    while True:
        idx = data.find(needle, start)
        if idx == -1:
            break
        hits.append(base + idx)
        start = idx + 1
    return hits


def find_arm_literal_loads(data: bytes, base: int, target_addr: int) -> list[int]:
    """ARM-mode `LDR Rd, [PC, #+/-imm12]` instructions whose computed literal address
    equals `target_addr`. Encoding: cond 01 0 P U 0 W 1 Rn Rd imm12, with Rn=1111(PC).
    Effective address = align4(instr_addr + 8) +/- imm12 (ARM PC is always +8).
    """
    results = []
    target_off = target_addr - base
    lo = max(0, target_off - ARM_LITERAL_RANGE)
    # scan every 4-byte-aligned word in [lo, target_off)
    for off in range(lo - (lo % 4), target_off, 4):
        if off + 4 > len(data):
            continue
        word, = struct.unpack_from("<I", data, off)
        # bits 27:25 = 010, bit22(B)=0 (word access), bit20(L)=1, bits19:16=1111 (Rn=PC)
        if (word & 0x0E500000) != 0x04100000:
            continue
        if ((word >> 16) & 0xF) != 0xF:
            continue
        imm12 = word & 0xFFF
        u_bit = (word >> 23) & 1
        instr_addr = base + off
        pc = (instr_addr + 8) & ~0x3
        eff_addr = pc + imm12 if u_bit else pc - imm12
        if eff_addr == target_addr:
            results.append(instr_addr)
    return results


def find_thumb_literal_loads(data: bytes, base: int, target_addr: int) -> list[int]:
    """THUMB-mode `LDR Rd, [PC, #imm8*4]` (encoding 01001 ddd iiiiiiii).
    Effective address = align4(instr_addr + 4) + imm8*4 (THUMB PC is +4, then aligned).
    """
    results = []
    target_off = target_addr - base
    lo = max(0, target_off - THUMB_LITERAL_RANGE)
    for off in range(lo - (lo % 2), target_off, 2):
        if off + 2 > len(data):
            continue
        halfword, = struct.unpack_from("<H", data, off)
        if (halfword & 0xF800) != 0x4800:
            continue
        imm8 = halfword & 0xFF
        instr_addr = base + off
        pc = (instr_addr + 4) & ~0x3
        eff_addr = pc + imm8 * 4
        if eff_addr == target_addr:
            results.append(instr_addr)
    return results


def disasm_context(data: bytes, base: int, addr: int, mode: int, count_before: int = 2, count_after: int = 12) -> None:
    """Best-effort disassembly print of a few instructions around `addr` for manual
    inspection. Not resilient (fine for a short, targeted window)."""
    md = capstone.Cs(capstone.CS_ARCH_ARM, mode)
    step = 4 if mode == capstone.CS_MODE_ARM else 2
    start_addr = addr - count_before * step
    off = start_addr - base
    length = (count_before + count_after) * step + 8
    if off < 0 or off + length > len(data):
        print(f"    (context out of range for this region)")
        return
    for insn in md.disasm(data[off:off + length], start_addr):
        marker = " <== literal load" if insn.address == addr else ""
        print(f"    0x{insn.address:08X}: {insn.mnemonic}\t{insn.op_str}{marker}")
        if insn.address > addr + count_after * step:
            break


def scan_region(name: str, data: bytes, base: int) -> None:
    print(f"\n=== {name} (0x{base:08X} - 0x{base + len(data):08X}, {len(data):#x} bytes) ===")

    raw_hits = find_raw_occurrences(data, base, G_SAVE_DATA_HOLDER_ADDR)
    if raw_hits:
        print(f"  Raw byte occurrences of 0x{G_SAVE_DATA_HOLDER_ADDR:08X} (literal pool slots): "
              f"{[hex(h) for h in raw_hits]}")
    else:
        print(f"  No raw occurrences of 0x{G_SAVE_DATA_HOLDER_ADDR:08X} in this region.")
        return

    any_refs = False
    for slot_addr in raw_hits:
        arm_refs = find_arm_literal_loads(data, base, slot_addr)
        thumb_refs = find_thumb_literal_loads(data, base, slot_addr)
        for ref_addr in arm_refs:
            any_refs = True
            print(f"\n  ARM  LDR at 0x{ref_addr:08X} loads literal @0x{slot_addr:08X} (=g_SaveDataHolder addr):")
            disasm_context(data, base, ref_addr, capstone.CS_MODE_ARM)
        for ref_addr in thumb_refs:
            any_refs = True
            print(f"\n  THUMB LDR at 0x{ref_addr:08X} loads literal @0x{slot_addr:08X} (=g_SaveDataHolder addr):")
            disasm_context(data, base, ref_addr, capstone.CS_MODE_THUMB)

    if not any_refs:
        print("  (raw bytes present, but no LDR-literal instruction in range references "
              "them as a PC-relative load - likely coincidental data, not a real code reference)")


if __name__ == "__main__":
    rom = load_rom()
    arm9, arm9_base = decompress_main_arm9(rom)
    scan_region("main ARM9", arm9, arm9_base)

    overlays = parse_overlay_table(rom)
    for ov in overlays:
        data = extract_overlay(rom, ov)
        scan_region(f"overlay {ov.overlay_id}", data, ov.ram_address)
