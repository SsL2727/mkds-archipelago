# mkds_disasm.py
#
# Reverse-engineering toolkit for the EU Mario Kart DS ROM, built 2026-08-04 while
# investigating whether the game's vanilla "always free" baseline content (8 starter
# characters, each character's first 2 karts, 4 of the 8 cups) can be suppressed via a
# RAM write - see NOTES.md's "ASM patch investigation" section for the full story and
# current status. Requires `pip install capstone` (a lightweight, pure-library ARM/THUMB
# disassembler - no devkitPro/NCPatcher/full SDK needed for READING code, only for
# actually building+injecting a patch, which is a separate, not-yet-attempted step).
#
# This does NOT modify the ROM - read-only analysis. Needs the EU ROM at ROM_PATH below.
#
# Usage:
#   from mkds_disasm import load_rom, decompress_main_arm9, decompress_overlay, find_callers
#
# Key findings so far (see NOTES.md for full detail):
# - The main ARM9 binary AND overlay files are compressed with Nintendo's "LZ-Overlay"/
#   BLZ backward-LZ scheme (confirmed via asmhack-examples/arm9.json's "compress": true).
#   lzovl_decompress() below is a careful line-by-line port of the authoritative
#   reference implementation (Barubary/dsdecmp, CSharp/DSDecmp/Formats/LZOvl.cs),
#   fetched and ported directly rather than reconstructed from memory - a subtly wrong
#   port would produce silently-corrupt (not obviously broken) output. Verified 3
#   separate times: each decompressed size exactly matched the ROM's own declared size
#   (arm9 header size field, or the overlay table's ram_size field) for that region.
# - Menu/scene code lives in dynamically-loaded OVERLAYS (NDS ROMs load different code
#   modules into the same RAM range at different times), not the main ARM9 binary -
#   parse_overlay_table()/extract_overlay() handle finding and decompressing these via
#   the NDS overlay table + FAT.
# - The game's unlock-check mechanism is confirmed: `CheckSavedSecretFlag_from_thumb`
#   (EU 0x02056DEC) takes a single bit-index parameter. Found live calls in overlay 1
#   (0x021804E0-0x021A99E0) passing 12 and 16 - which EXACTLY match
#   rom_addresses.UNLOCK_BIT_LIGHTNING_CUP (bit 12) and UNLOCK_BIT_MIRROR_MODE (bit 16)
#   from this project's independent, empirical RAM bit-mapping - strong cross-validation
#   of that whole earlier investigation via a completely different method.
# - Confirmed (via embedded asset-filename strings, e.g. "common/select_cup_course_ta_m.
#   bncl", "ta/select_ghost_s.nscr", "gp/select_engine_m.bncl") that overlay 1
#   (0x021804E0-0x021A99E0, file_id=2) IS the real menu/select-screen overlay - covers
#   cup/course select, time trial ghost select, "engine" (CC class, where Mirror Mode's
#   check lives) select, option select, battle stage select. Overlay 0 (SAME ram_address,
#   the mutually-exclusive alternative occupying that RAM slot at a different time) has
#   NO similar strings at all - likely a different scene entirely (untested which).
# - Searched exhaustively for character-select-specific strings in both overlay 0 and 1
#   (full names "mario"/"luigi"/etc, and the 2-letter codes items.py's kart names already
#   use - "_mr"/"_lg"/"_wr"/"_bw"/"_db"/"_ds"/"_wl"/"_rb"/"_pc"/"_ys"/"_td") - found
#   NOTHING character-select-related in either. This is a real, currently-unexplained gap:
#   overlay 1 clearly has RELATED select-screen logic and assets, but nothing tying
#   character selection specifically to it has been found by any method tried so far
#   (function calls OR strings).
# - Tangential finding worth flagging separately: mkds-eu-types.h's CharacterId enum has
#   CharacterId_Count = 13, not 12 - CharacterId_Heyho_ShyGuy = 12 is a 13th character
#   that's never been seen in any testing this project has done. Possibly cut/unused
#   content, possibly a real character nobody has looked for - not investigated further,
#   out of scope for the unlock-suppression question but worth a look sometime.
# - NOT yet found: any call checking the other 7 lockable bits (Star/Special/Leaf cups,
#   Dry Bones, Daisy, Waluigi, R.O.B.), or the actual character-select/cup-select grid-
#   population loop, across the main ARM9 binary + all 4 overlays (0, 1, 2, 3), by either
#   function-call scanning or string search. Candidate next steps if resumed: search for
#   INLINE bit-test patterns against the known UNLOCK_FLAGS_ADDRESS offset (+0x70 from
#   g_SaveDataHolder) directly, rather than assuming a function call happens at all -
#   character-select may just load the flags word once and AND/TST against it inline,
#   which would never show up in a "find calls to X" search regardless of how thorough.

import struct
from typing import NamedTuple, Optional

import capstone

ROM_PATH = r"F:\Mario Kart DS AP\0201 - Mario Kart DS (E)(Spliff).nds"


def load_rom(path: str = ROM_PATH) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def lzovl_decompress(data: bytes, is_arm9: bool = True) -> bytes:
    """Nintendo's "LZ-Overlay"/BLZ backward-LZ decompression, used for arm9.bin and NDS
    overlay files. Ported from Barubary/dsdecmp's LZOvl.cs (the authoritative reference
    implementation) - see module docstring. `is_arm9=True` ignores the last 0xC bytes of
    `data`, matching arm9.bin's 3 extra trailing u32 values (per the original's own
    comment: "these 12 bytes also should not be included in the computation of the
    output size"). Overlay files don't have this quirk (`is_arm9=False`).
    """
    in_length = len(data) - (0xC if is_arm9 else 0)

    extra_size = int.from_bytes(data[in_length - 4:in_length], "little")

    if extra_size == 0:
        return data[:in_length - 4]

    header_size = data[in_length - 5]

    compressed_size_bytes = data[in_length - 8:in_length - 5]
    compressed_size = (
        compressed_size_bytes[0]
        | (compressed_size_bytes[1] << 8)
        | (compressed_size_bytes[2] << 16)
    )
    compressed_size -= header_size

    if compressed_size + header_size >= in_length:
        compressed_size = in_length - header_size

    raw_prefix_len = in_length - header_size - compressed_size
    raw_prefix = data[0:raw_prefix_len]

    buffer = data[raw_prefix_len: raw_prefix_len + compressed_size]
    assert len(buffer) == compressed_size

    decompressed_length = compressed_size + header_size + extra_size
    outbuffer = bytearray(decompressed_length)

    current_out_size = 0
    read_bytes = 0
    flags = 0
    mask = 1

    while current_out_size < decompressed_length:
        if mask == 1:
            if read_bytes >= compressed_size:
                raise ValueError("ran out of compressed data (flags byte)")
            flags = buffer[len(buffer) - 1 - read_bytes]
            read_bytes += 1
            mask = 0x80
        else:
            mask >>= 1

        if flags & mask:
            if read_bytes + 1 >= in_length:
                raise ValueError("ran out of compressed data (len/disp bytes)")
            byte1 = buffer[compressed_size - 1 - read_bytes]
            read_bytes += 1
            byte2 = buffer[compressed_size - 1 - read_bytes]
            read_bytes += 1

            length = (byte1 >> 4) + 3
            disp = ((byte1 & 0x0F) << 8) | byte2
            disp += 3

            if disp > current_out_size:
                if current_out_size < 2:
                    raise ValueError(
                        f"invalid data: disp 0x{disp:X} > current_out_size 0x{current_out_size:X}"
                    )
                disp = 2

            buf_idx = current_out_size - disp
            for _ in range(length):
                nxt = outbuffer[decompressed_length - 1 - buf_idx]
                buf_idx += 1
                outbuffer[decompressed_length - 1 - current_out_size] = nxt
                current_out_size += 1
        else:
            if read_bytes >= in_length:
                raise ValueError("ran out of compressed data (raw byte)")
            nxt = buffer[len(buffer) - 1 - read_bytes]
            read_bytes += 1
            outbuffer[decompressed_length - 1 - current_out_size] = nxt
            current_out_size += 1

    return raw_prefix + bytes(outbuffer)


def decompress_main_arm9(rom: bytes) -> tuple[bytes, int]:
    """Returns (decompressed_bytes, runtime_base_address)."""
    arm9_rom_offset, = struct.unpack_from("<I", rom, 0x20)
    arm9_ram_address, = struct.unpack_from("<I", rom, 0x28)
    arm9_size, = struct.unpack_from("<I", rom, 0x2C)
    arm9 = rom[arm9_rom_offset: arm9_rom_offset + arm9_size]
    return lzovl_decompress(arm9, is_arm9=True), arm9_ram_address


class OverlayEntry(NamedTuple):
    overlay_id: int
    ram_address: int
    ram_size: int
    bss_size: int
    file_id: int
    compressed_size: int
    is_compressed: bool


def parse_overlay_table(rom: bytes) -> list[OverlayEntry]:
    """Parses the ARM9 overlay table (NDS header 0x50/0x54) - each 32-byte entry
    describes one dynamically-loadable code module and which FAT file_id holds its data.
    """
    ov9_offset, = struct.unpack_from("<I", rom, 0x50)
    ov9_size, = struct.unpack_from("<I", rom, 0x54)
    entries = []
    for i in range(ov9_size // 32):
        base = ov9_offset + i * 32
        ov_id, ram_addr, ram_size, bss_size, si_start, si_end, file_id, comp_and_flags = (
            struct.unpack_from("<8I", rom, base)
        )
        entries.append(OverlayEntry(
            overlay_id=ov_id,
            ram_address=ram_addr,
            ram_size=ram_size,
            bss_size=bss_size,
            file_id=file_id,
            compressed_size=comp_and_flags & 0xFFFFFF,
            is_compressed=bool((comp_and_flags >> 24) & 1),
        ))
    return entries


def extract_overlay(rom: bytes, entry: OverlayEntry) -> bytes:
    """Reads the overlay's raw file data via the FAT (NDS header 0x48) and decompresses
    it if needed. Returned bytes map to runtime addresses starting at entry.ram_address.
    """
    fat_offset, = struct.unpack_from("<I", rom, 0x48)
    start, end = struct.unpack_from("<II", rom, fat_offset + entry.file_id * 8)
    raw = rom[start:end]
    if entry.is_compressed:
        return lzovl_decompress(raw, is_arm9=False)
    return raw


def resilient_scan_for_calls(
    data: bytes, base: int, mode: int, targets: dict[int, str]
) -> list[tuple[int, str, int, str]]:
    """Finds every BL/BLX call site in `data` (mapped to runtime addresses starting at
    `base`) targeting one of `targets`' addresses. `mode` is capstone.CS_MODE_ARM or
    CS_MODE_THUMB - call once per mode, since NDS code mixes both and a linear
    disassembly pass only makes sense within one consistent mode at a time.

    Uses a RESILIENT linear disassembly (resyncs to the next aligned position after any
    decode failure) rather than capstone's default disasm() generator, which silently
    stops at the FIRST undecodable instruction - fatal for scanning a real binary that
    mixes code, data, and padding. (A cheaper byte-pattern prefilter was tried first and
    found nothing - only this resilient version, once validated against a known call
    site, turned out to be reliable.)
    """
    mode_name = "ARM" if mode == capstone.CS_MODE_ARM else "THUMB"
    step = 4 if mode == capstone.CS_MODE_ARM else 2
    md = capstone.Cs(capstone.CS_ARCH_ARM, mode)
    results = []
    n = len(data)
    off = 0
    while off < n - 4:
        addr = base + off
        consumed = 0
        for insn in md.disasm(data[off:off + 0x1000], addr):
            consumed = (insn.address + insn.size) - addr
            if insn.mnemonic in ("bl", "blx"):
                op = insn.op_str.lstrip("#")
                try:
                    target = int(op, 16)
                except ValueError:
                    target = None
                if target in targets:
                    results.append((insn.address, insn.mnemonic, target, mode_name))
        if consumed == 0:
            consumed = step
        off += consumed
    return results


def disasm_at(data: bytes, base: int, addr: int, length: int, mode: int) -> None:
    """Prints a linear disassembly of `length` bytes starting at runtime address `addr`,
    for quick interactive inspection (not resilient - stops at the first bad opcode,
    which is fine for eyeballing a short, known-good range).
    """
    off = addr - base
    md = capstone.Cs(capstone.CS_ARCH_ARM, mode)
    for insn in md.disasm(data[off:off + length], addr):
        print(f"0x{insn.address:08X}: {insn.mnemonic}\t{insn.op_str}")


# Known EU function addresses relevant to unlock-flag checking (mkds-eu-symbols.x).
SECRET_FLAG_FUNCTIONS = {
    0x0205FBB8: "CheckSecretFlag",
    0x02046648: "HasSomeSecretFlag",
    0x02056DEC: "CheckSavedSecretFlag_from_thumb",
    0x02056E00: "CheckSecretFlagWith_from_thumb",
    0x02056E24: "SetSavedSecretFlag_from_thumb",
    0x02090B24: "GetCurrentCharacterUnlockSecretFlags",
    0x02090CF8: "GetCurrentCupUnlockSecretFlags",
    0x02090FF4: "GetCurrentUnlockedSecretFlags",
}


if __name__ == "__main__":
    rom = load_rom()
    arm9, arm9_base = decompress_main_arm9(rom)
    print(f"main ARM9: 0x{len(arm9):X} bytes @ 0x{arm9_base:08X}")

    overlays = parse_overlay_table(rom)
    decompressed_overlays = {}
    for ov in overlays:
        data = extract_overlay(rom, ov)
        decompressed_overlays[ov.overlay_id] = data
        print(f"overlay {ov.overlay_id}: 0x{len(data):X} bytes @ 0x{ov.ram_address:08X} "
              f"(declared ram_size 0x{ov.ram_size:X}, {'match' if len(data) == ov.ram_size else 'MISMATCH'})")

    print()
    print("Scanning for calls to known secret-flag-check functions...")
    all_results = []
    all_results += resilient_scan_for_calls(arm9, arm9_base, capstone.CS_MODE_ARM, SECRET_FLAG_FUNCTIONS)
    all_results += resilient_scan_for_calls(arm9, arm9_base, capstone.CS_MODE_THUMB, SECRET_FLAG_FUNCTIONS)
    for ov in overlays:
        data = decompressed_overlays[ov.overlay_id]
        all_results += resilient_scan_for_calls(data, ov.ram_address, capstone.CS_MODE_ARM, SECRET_FLAG_FUNCTIONS)
        all_results += resilient_scan_for_calls(data, ov.ram_address, capstone.CS_MODE_THUMB, SECRET_FLAG_FUNCTIONS)

    for addr, mnem, target, mode_name in sorted(all_results):
        print(f"0x{addr:08X} ({mode_name}): {mnem} -> {SECRET_FLAG_FUNCTIONS[target]}")
