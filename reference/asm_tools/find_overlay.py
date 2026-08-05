import struct

ROM_PATH = r"F:\Mario Kart DS AP\0201 - Mario Kart DS (E)(Spliff).nds"
with open(ROM_PATH, "rb") as f:
    rom = f.read()

fat_offset, = struct.unpack_from("<I", rom, 0x48)
fat_size, = struct.unpack_from("<I", rom, 0x4C)
ov9_offset, = struct.unpack_from("<I", rom, 0x50)
ov9_size, = struct.unpack_from("<I", rom, 0x54)

print(f"FAT: offset=0x{fat_offset:08X} size=0x{fat_size:08X} ({fat_size // 8} entries)")
print(f"ARM9 overlay table: offset=0x{ov9_offset:08X} size=0x{ov9_size:08X} ({ov9_size // 32} entries)")
print()

TARGET_ADDRS = [0x2112ef0, 0x210be20]

entry_count = ov9_size // 32
print(f"{'ID':>3} {'ram_addr':>10} {'ram_size':>10} {'ram_end':>10} {'bss_size':>10} {'file_id':>7} {'comp_size':>9} {'flags':>5}")
for i in range(entry_count):
    base = ov9_offset + i * 32
    ov_id, ram_addr, ram_size, bss_size, si_start, si_end, file_id, comp_and_flags = struct.unpack_from("<8I", rom, base)
    comp_size = comp_and_flags & 0xFFFFFF
    flags = (comp_and_flags >> 24) & 0xFF
    ram_end = ram_addr + ram_size
    hit = any(ram_addr <= t < ram_end for t in TARGET_ADDRS)
    marker = "  <== CONTAINS TARGET" if hit else ""
    print(f"{ov_id:>3} 0x{ram_addr:08X} 0x{ram_size:08X} 0x{ram_end:08X} 0x{bss_size:08X} {file_id:>7} 0x{comp_size:07X} {flags:>5}{marker}")
