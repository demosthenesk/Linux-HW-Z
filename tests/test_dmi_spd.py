"""Unit checks for the SMBIOS parser with a synthetic table (run: python3 -m tests.test_dmi_spd)."""
import struct
from hwz.probes import dmi, memory


def structure(typ, handle, body: bytes, strings):
    head = bytes([typ, 4 + len(body)]) + struct.pack("<H", handle)
    tail = b"".join(s.encode() + b"\0" for s in strings) + b"\0"
    if not strings:
        tail = b"\0\0"
    return head + body + tail


def t17(handle, size_mb, loc, bank, mtype, speed, mfr, part, rank=1):
    b = bytearray(0x5C - 4)
    def put(off, fmt, v):
        struct.pack_into(fmt, b, off - 4, v)
    put(0x04, "<H", 0x1000)
    put(0x08, "<H", 64); put(0x0A, "<H", 64)
    put(0x0C, "<H", size_mb)
    b[0x0E - 4] = 0x0D
    b[0x10 - 4] = 1; b[0x11 - 4] = 2
    b[0x12 - 4] = mtype
    put(0x15, "<H", speed)
    b[0x17 - 4] = 3; b[0x18 - 4] = 4; b[0x1A - 4] = 5
    b[0x1B - 4] = rank
    put(0x20, "<H", speed)
    put(0x26, "<H", 1200)
    return structure(17, handle, bytes(b), [loc, bank, mfr, "1234ABCD", part])


def t4():
    b = bytearray(0x30 - 4)
    b[0x04 - 4] = 1
    b[0x11 - 4] = 0x80 | 8          # 0.8 V
    struct.pack_into("<H", b, 0x12 - 4, 100)
    struct.pack_into("<H", b, 0x14 - 4, 5000)
    b[0x19 - 4] = 0x41              # Socket BGA1744
    return structure(4, 0x40, bytes(b), ["U3E1"])


table = t4() + t17(0x1001, 8192, "DIMM A", "BANK 0", 0x1A, 3200, "SK Hynix", "HMA81GS6DJR8N-XN") + \
    t17(0x1002, 8192, "DIMM B", "BANK 2", 0x1A, 3200, "SK Hynix", "HMA81GS6DJR8N-XN") + structure(127, 0xFEFF, b"", [])
res = dmi.parse_table(table)
p = res["processors"][0]
assert p["upgrade"] == "Socket BGA1744", p
assert p["voltage"] == "0.80 V", p
m = res["memory"]
assert len(m) == 2 and m[0]["size_mb"] == 8192 and m[0]["type"] == "DDR4" and m[0]["form"] == "SO-DIMM", m
assert m[0]["manufacturer"] == "SK Hynix" and m[0]["part"] == "HMA81GS6DJR8N-XN", m[0]
s = memory.summary(res, [])
assert s["installed_mb"] == 16384 and s["configured_speed"] == 3200, s
print("channels:", s["channels"], "| summary ok:", s["type"], s["installed_mb"], s["slots_used"], s["slots_total"])
