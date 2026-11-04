"""Mainboard / BIOS identification (DMI) and a small SMBIOS table parser.

The /sys/class/dmi/id files are readable by every user (except serial
numbers).  The full SMBIOS table (memory slots, socket, voltage) needs root;
it is fetched once by the administrator helper and parsed here.
"""

from __future__ import annotations

import struct

from ..sysfs import read

ID = "/sys/class/dmi/id"


def basic() -> dict[str, str]:
    keys = ["sys_vendor", "product_name", "product_version", "product_family", "product_sku",
            "board_vendor", "board_name", "board_version", "bios_vendor", "bios_version",
            "bios_date", "bios_release", "chassis_type", "chassis_vendor", "ec_firmware_release"]
    out = {}
    for k in keys:
        v = read(f"{ID}/{k}")
        if v and v.lower() not in ("to be filled by o.e.m.", "default string", "not applicable",
                                   "system product name", "system version", "none"):
            out[k] = v
    return out


CHASSIS = {3: "Desktop", 4: "Low Profile Desktop", 6: "Mini Tower", 7: "Tower", 8: "Portable",
           9: "Laptop", 10: "Notebook", 11: "Hand Held", 13: "All in One", 14: "Sub Notebook",
           30: "Tablet", 31: "Convertible", 32: "Detachable", 35: "Mini PC", 36: "Stick PC"}

MEM_TYPES = {0x12: "DDR", 0x13: "DDR2", 0x14: "DDR2 FB-DIMM", 0x18: "DDR3", 0x1A: "DDR4",
             0x1B: "LPDDR", 0x1C: "LPDDR2", 0x1D: "LPDDR3", 0x1E: "LPDDR4", 0x1F: "Logical non-volatile",
             0x20: "HBM", 0x21: "HBM2", 0x22: "DDR5", 0x23: "LPDDR5", 0x24: "HBM3"}
FORM_FACTORS = {0x01: "Other", 0x02: "Unknown", 0x03: "SIMM", 0x09: "DIMM", 0x0B: "Row of chips",
                0x0D: "SO-DIMM", 0x0F: "FB-DIMM", 0x10: "Die", 0x11: "CAMM"}
UPGRADES = ["", "Other", "Unknown", "Daughter Board", "ZIF Socket", "Replaceable Piggy Back", "None",
            "LIF Socket", "Slot 1", "Slot 2", "370-pin Socket", "Slot A", "Slot M", "Socket 423",
            "Socket A (Socket 462)", "Socket 478", "Socket 754", "Socket 940", "Socket 939",
            "Socket mPGA604", "Socket LGA771", "Socket LGA775", "Socket S1", "Socket AM2",
            "Socket F (1207)", "Socket LGA1366", "Socket G34", "Socket AM3", "Socket C32",
            "Socket LGA1156", "Socket LGA1567", "Socket PGA988A", "Socket BGA1288", "Socket rPGA988B",
            "Socket BGA1023", "Socket BGA1224", "Socket BGA1155", "Socket LGA1356", "Socket LGA2011",
            "Socket FS1", "Socket FS2", "Socket FM1", "Socket FM2", "Socket LGA2011-3",
            "Socket LGA1356-3", "Socket LGA1150", "Socket BGA1168", "Socket BGA1234", "Socket BGA1364",
            "Socket AM4", "Socket LGA1151", "Socket BGA1356", "Socket BGA1440", "Socket BGA1515",
            "Socket LGA3647-1", "Socket SP3", "Socket SP3r2", "Socket LGA2066", "Socket BGA1392",
            "Socket BGA1510", "Socket BGA1528", "Socket LGA4189", "Socket LGA1200", "Socket LGA4677",
            "Socket LGA1700", "Socket BGA1744", "Socket BGA1781", "Socket BGA1211", "Socket BGA2422",
            "Socket LGA1211", "Socket LGA2422", "Socket LGA5773", "Socket BGA5773", "Socket AM5",
            "Socket SP5", "Socket SP6", "Socket BGA883", "Socket BGA1190", "Socket BGA4129",
            "Socket LGA4710", "Socket LGA7529"]


def _structures(table: bytes):
    i, n = 0, len(table)
    while i + 4 <= n:
        typ, length = table[i], table[i + 1]
        if length < 4:
            break
        handle = struct.unpack_from("<H", table, i + 2)[0]
        formatted = table[i:i + length]
        j = i + length
        strings = []
        start = j
        while j + 1 < n and not (table[j] == 0 and table[j + 1] == 0):
            if table[j] == 0:
                strings.append(table[start:j].decode("latin-1", "replace").strip())
                start = j + 1
            j += 1
        if j > start:
            strings.append(table[start:j].decode("latin-1", "replace").strip())
        yield typ, handle, formatted, strings
        if typ == 127:
            break
        i = j + 2


def _s(fmt: bytes, strings: list[str], off: int) -> str:
    if off >= len(fmt):
        return ""
    idx = fmt[off]
    if idx == 0 or idx > len(strings):
        return ""
    v = strings[idx - 1]
    return "" if v.lower() in ("not specified", "unknown", "to be filled by o.e.m.", "none") else v


def _w(fmt: bytes, off: int) -> int | None:
    return struct.unpack_from("<H", fmt, off)[0] if off + 2 <= len(fmt) else None


def _d(fmt: bytes, off: int) -> int | None:
    return struct.unpack_from("<I", fmt, off)[0] if off + 4 <= len(fmt) else None


def parse_table(table: bytes) -> dict:
    res = {"processors": [], "memory": [], "arrays": []}
    for typ, handle, f, s in _structures(table):
        if typ == 4:
            volt = f[0x11] if len(f) > 0x11 else 0
            if volt & 0x80:
                vtext = f"{(volt & 0x7F) / 10:.2f} V"
            else:
                vtext = " / ".join(v for b, v in ((1, "5.0 V"), (2, "3.3 V"), (4, "2.9 V")) if volt & b)
            up = f[0x19] if len(f) > 0x19 else 0
            res["processors"].append({
                "socket": _s(f, s, 0x04), "manufacturer": _s(f, s, 0x07), "version": _s(f, s, 0x10),
                "voltage": vtext, "ext_clock": _w(f, 0x12), "max_speed": _w(f, 0x14),
                "cur_speed": _w(f, 0x16), "upgrade": UPGRADES[up] if 0 < up < len(UPGRADES) else "",
            })
        elif typ == 16:
            cap = _d(f, 0x07)
            if cap == 0x80000000 and len(f) >= 0x17:
                cap_kb = struct.unpack_from("<Q", f, 0x0F)[0] // 1024
            else:
                cap_kb = cap
            res["arrays"].append({"handle": handle, "max_kb": cap_kb, "slots": _w(f, 0x0D),
                                  "use": f[0x05] if len(f) > 5 else 0})
        elif typ == 17:
            size = _w(f, 0x0C) or 0
            if size in (0, 0xFFFF):
                size_mb = 0
            elif size == 0x7FFF:
                size_mb = (_d(f, 0x1C) or 0) & 0x7FFFFFFF
            elif size & 0x8000:
                size_mb = (size & 0x7FFF) // 1024
            else:
                size_mb = size
            speed = _w(f, 0x15) or 0
            if speed == 0xFFFF:
                speed = _d(f, 0x54) or 0
            conf = _w(f, 0x20) or 0
            if conf == 0xFFFF:
                conf = _d(f, 0x58) or 0
            mtype = f[0x12] if len(f) > 0x12 else 0
            res["memory"].append({
                "handle": handle, "array": _w(f, 0x04), "size_mb": size_mb,
                "form": FORM_FACTORS.get(f[0x0E] if len(f) > 0x0E else 0, ""),
                "locator": _s(f, s, 0x10), "bank": _s(f, s, 0x11),
                "type": MEM_TYPES.get(mtype, ""), "speed": speed, "configured_speed": conf,
                "manufacturer": _s(f, s, 0x17), "serial": _s(f, s, 0x18), "part": _s(f, s, 0x1A),
                "rank": (f[0x1B] & 0x0F) if len(f) > 0x1B else 0,
                "total_width": _w(f, 0x08), "data_width": _w(f, 0x0A),
                "voltage_mv": _w(f, 0x26) or _w(f, 0x22) or 0,
            })
    return res


def channels(mem: list[dict]) -> str:
    pop = [m for m in mem if m["size_mb"]]
    if not pop:
        return ""
    keys = set()
    for m in pop:
        loc = f"{m['bank']} {m['locator']}".upper()
        ch = None
        for tag in ("CHANNEL", "CHAN", "CH"):
            if tag in loc:
                ch = loc.split(tag, 1)[1].strip(" _-")[:1]
                break
        keys.add(ch or loc)
    n = len(keys)
    # LPDDR4/5 packages expose several 16/32-bit channels but behave as "dual"/"quad"
    names = {1: "Single", 2: "Dual", 3: "Triple", 4: "Quad", 6: "6 x", 8: "8 x", 12: "12 x"}
    return names.get(n, f"{n} x")
