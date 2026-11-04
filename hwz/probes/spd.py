"""Memory module SPD EEPROM decoding (DDR3, DDR4, DDR5).

The EEPROM contents come from the ee1004 (DDR4) / at24 (DDR3) / spd5118 (DDR5)
kernel drivers.  Their files are usually world-readable once the driver is
bound; the administrator helper loads the drivers when they are missing.
"""

from __future__ import annotations

import math
import struct

from ..sysfs import glob, read, read_bytes

# JEDEC JEP106: (bank, code without parity) -> name
JEDEC = {
    (1, 0x01): "AMD", (1, 0x04): "Fujitsu", (1, 0x07): "Hitachi", (1, 0x10): "NEC",
    (1, 0x2C): "Micron Technology", (1, 0x4F): "Transcend Information", (1, 0x7A): "Apacer Technology",
    (1, 0x94): "Smart Modular", (1, 0x97): "Texas Instruments", (1, 0x98): "Toshiba",
    (1, 0xAD): "SK Hynix", (1, 0xB3): "Integrated Device Technology", (1, 0xC1): "Infineon (Siemens)",
    (1, 0xCE): "Samsung", (1, 0xFE): "Elpida",
    (2, 0x98): "Kingston", (2, 0x9E): "Mushkin", (2, 0xFE): "Mushkin",
    (3, 0x0B): "Nanya Technology", (3, 0x9E): "Corsair", (3, 0x25): "Kingmax Semiconductor",
    (3, 0xD9): "Renesas",
    (4, 0x0B): "Nanya Technology", (4, 0x43): "Ramaxel Technology", (4, 0xF1): "Avant Technology",
    (5, 0x43): "Ramaxel Technology", (5, 0xCB): "A-DATA Technology", (5, 0xCD): "G.Skill",
    (5, 0xEF): "Team Group",
    (6, 0x02): "Patriot Memory", (6, 0x9B): "Crucial Technology", (6, 0x51): "Qimonda",
    (7, 0x57): "AMD (Radeon)", (7, 0x4F): "Kingbank",
    (9, 0x8A): "CXMT (ChangXin)", (10, 0x7D): "Asgard", (11, 0x1B): "Lexar",
}


def jedec_name(cont: int, code: int) -> str:
    bank = (cont & 0x7F) + 1
    c = code & 0x7F
    for (b, k), name in JEDEC.items():
        if b == bank and (k & 0x7F) == c:
            return name
    if code in (0, 0xFF):
        return ""
    return f"Bank {bank}, 0x{code:02X}"


def _bcd(b: int) -> int:
    return (b >> 4) * 10 + (b & 0xF)


def _fine(b: int) -> int:
    return b - 256 if b > 127 else b


DDR4_BINS = [667, 800, 933, 1067, 1200, 1333, 1467, 1600]        # MHz (half data rate)
DDR3_BINS = [400, 533, 667, 800, 933, 1067]
DDR5_BINS = [1600, 1800, 2000, 2200, 2400, 2600, 2800, 3000, 3200, 3600, 4000, 4400]

MODULE_TYPES_DDR4 = {1: "RDIMM", 2: "UDIMM", 3: "SO-DIMM", 4: "LRDIMM", 5: "Mini-RDIMM", 6: "Mini-UDIMM",
                     8: "72b-SO-RDIMM", 9: "72b-SO-UDIMM", 12: "16b-SO-DIMM", 13: "32b-SO-DIMM"}
MODULE_TYPES_DDR5 = {1: "RDIMM", 2: "UDIMM", 3: "SO-DIMM", 4: "LRDIMM", 5: "CUDIMM", 6: "CSODIMM",
                     7: "MRDIMM", 8: "CAMM2", 10: "DDIMM", 11: "Solder down"}


def _timings_table(bins, tck_min, cls, taa, trcd, trp, tras, trc, volts, clk_from_tck=True):
    rows = []
    for mhz in bins:
        tck = 1000.0 / mhz
        if tck < tck_min - 0.01:
            continue
        cl = math.ceil(taa / tck - 0.025)
        cands = [c for c in sorted(cls) if c >= cl]
        if not cands:
            continue
        cl = cands[0]
        rows.append({"freq": mhz, "cl": cl, "trcd": math.ceil(trcd / tck - 0.025),
                     "trp": math.ceil(trp / tck - 0.025), "tras": math.ceil(tras / tck - 0.025),
                     "trc": math.ceil(trc / tck - 0.025), "voltage": volts})
    # keep the fastest few, distinct by CL (what CPU-Z shows as JEDEC #1..#n)
    seen, out = set(), []
    for r in reversed(rows):
        if r["cl"] in seen:
            continue
        seen.add(r["cl"])
        out.append(r)
    return list(reversed(out))[-6:]


def _std_mhz(mhz: float, bins) -> int:
    for b in bins:
        if abs(mhz - b) / b < 0.012:
            return b
    return round(mhz)


def decode(data: bytes) -> dict | None:
    if not data or len(data) < 128:
        return None
    t = data[2]
    if t == 0x0C and len(data) >= 384:
        return _ddr4(data)
    if t in (0x12, 0x13, 0x15) and len(data) >= 640:
        return _ddr5(data)
    if t == 0x0B:
        return _ddr3(data)
    return {"type": {0x0E: "LPDDR3", 0x10: "LPDDR4", 0x11: "LPDDR4X"}.get(t, f"type 0x{t:02X}")}


def _ascii(b: bytes) -> str:
    return b.decode("ascii", "replace").replace("\x00", "").strip()


def _ddr4(d: bytes) -> dict:
    mtb, ftb = 0.125, 0.001
    density_mb = 256 << (d[4] & 0x0F)
    dev_width = 4 << (d[12] & 0x07)
    ranks = ((d[12] >> 3) & 0x07) + 1
    bus = 8 << (d[13] & 0x07)
    ecc = bool(d[13] & 0x18)
    signal = d[6] & 0x03
    dies = ((d[6] >> 4) & 0x07) + 1
    logical = ranks * (dies if signal == 2 else 1)
    size_mb = density_mb // 8 * bus // dev_width * logical
    tck = d[18] * mtb + _fine(d[125]) * ftb
    cls_mask = d[20] | d[21] << 8 | d[22] << 16 | (d[23] & 0x3F) << 24
    base = 23 if d[23] & 0x80 else 7
    cls = [base + i for i in range(30) if cls_mask >> i & 1]
    taa = d[24] * mtb + _fine(d[123]) * ftb
    trcd = d[25] * mtb + _fine(d[122]) * ftb
    trp = d[26] * mtb + _fine(d[121]) * ftb
    tras = (((d[27] & 0x0F) << 8) | d[28]) * mtb
    trc = (((d[27] & 0xF0) << 4) | d[29]) * mtb + _fine(d[120]) * ftb
    max_mhz = 1000.0 / tck if tck else 0
    res = {
        "type": "DDR4", "module": MODULE_TYPES_DDR4.get(d[3] & 0x0F, ""),
        "size_mb": size_mb, "ranks": ranks, "dev_width": dev_width, "ecc": ecc,
        "registered": (d[3] & 0x0F) in (1, 4, 5, 8),
        "max_mhz": _std_mhz(max_mhz, DDR4_BINS), "speed_name": f"DDR4-{round(max_mhz * 2 / 100) * 100 if max_mhz else 0}",
        "voltage": "1.20 V",
        "timings": _timings_table(DDR4_BINS, tck, cls, taa, trcd, trp, tras, trc, "1.20 V"),
    }
    if len(d) >= 512:
        res.update(_ident(d, 320, 323, 325, 329, 20, 350))
    if len(d) >= 512 and d[384] == 0x0C and d[385] == 0x4A:
        res["ext"] = "XMP 2.0"
    return res


def _ddr5(d: bytes) -> dict:
    dens = {1: 4, 2: 8, 3: 12, 4: 16, 5: 24, 6: 32, 7: 48, 8: 64}.get(d[4] & 0x1F, 0)
    dpp = {0: 1, 2: 2, 3: 4, 4: 8, 5: 16}.get(d[4] >> 5, 1)
    width = 4 << (d[6] >> 5)
    ranks = ((d[234] >> 3) & 0x07) + 1
    bus = 8 << (d[235] & 0x07)
    subch = ((d[235] >> 5) & 0x03) + 1
    size_mb = subch * (bus // width) * dpp * dens * 1024 // 8 * ranks
    ps = lambda o: struct.unpack_from("<H", d, o)[0] / 1000.0  # noqa: E731
    tck = ps(20)
    cls_mask = int.from_bytes(d[24:29], "little")
    cls = [20 + 2 * i for i in range(40) if cls_mask >> i & 1]
    taa, trcd, trp, tras, trc = ps(30), ps(32), ps(34), ps(36), ps(38)
    max_mhz = 1000.0 / tck if tck else 0
    res = {
        "type": "DDR5", "module": MODULE_TYPES_DDR5.get(d[3] & 0x0F, ""), "size_mb": size_mb,
        "ranks": ranks, "dev_width": width, "ecc": bool(d[235] & 0x18), "registered": (d[3] & 0x0F) in (1, 4, 7),
        "max_mhz": _std_mhz(max_mhz, DDR5_BINS), "speed_name": f"DDR5-{round(max_mhz * 2 / 100) * 100 if max_mhz else 0}",
        "voltage": "1.10 V",
        "timings": _timings_table(DDR5_BINS, tck, cls, taa, trcd, trp, tras, trc, "1.10 V"),
    }
    if len(d) >= 554:
        res.update(_ident(d, 512, 515, 517, 521, 30, 552))
    if len(d) >= 1024 and d[640] == 0x0C and d[641] == 0x4A:
        res["ext"] = "XMP 3.0"
    if len(d) >= 1024 and d[832] == 0x4D and d[833] == 0x45:
        res["ext"] = (res.get("ext", "") + " EXPO").strip()
    return res


def _ddr3(d: bytes) -> dict:
    mtb = d[10] / d[11] if d[11] else 0.125
    ftb = ((d[9] >> 4) / (d[9] & 0x0F) / 1000) if d[9] & 0x0F else 0
    density_mb = 256 << (d[4] & 0x0F)
    dev_width = 4 << (d[7] & 0x07)
    ranks = ((d[7] >> 3) & 0x07) + 1
    bus = 8 << (d[8] & 0x07)
    size_mb = density_mb // 8 * bus // dev_width * ranks
    tck = d[12] * mtb + _fine(d[34]) * ftb
    cls_mask = d[14] | d[15] << 8
    cls = [4 + i for i in range(16) if cls_mask >> i & 1]
    taa = d[16] * mtb + _fine(d[35]) * ftb
    trcd, trp = d[18] * mtb, d[20] * mtb
    tras = (((d[21] & 0x0F) << 8) | d[22]) * mtb
    trc = (((d[21] & 0xF0) << 4) | d[23]) * mtb
    v = "1.35 V" if d[6] & 0x02 else "1.50 V"
    max_mhz = 1000.0 / tck if tck else 0
    res = {"type": "DDR3", "module": {1: "RDIMM", 2: "UDIMM", 3: "SO-DIMM"}.get(d[3] & 0x0F, ""),
           "size_mb": size_mb, "ranks": ranks, "dev_width": dev_width, "ecc": bool(d[8] & 0x18),
           "registered": (d[3] & 0x0F) == 1, "max_mhz": _std_mhz(max_mhz, DDR3_BINS),
           "speed_name": f"DDR3-{round(max_mhz * 2 / 100) * 100 if max_mhz else 0}", "voltage": v,
           "timings": _timings_table(DDR3_BINS, tck, cls, taa, trcd, trp, tras, trc, v)}
    if len(d) >= 148:
        mfr = jedec_name(d[117], d[118])
        res.update({"manufacturer": mfr, "year": 2000 + _bcd(d[120]) if d[120] else None,
                    "week": _bcd(d[121]) if d[121] else None,
                    "serial": d[122:126].hex().upper(), "part": _ascii(d[128:146]),
                    "dram_manufacturer": jedec_name(d[148], d[149]) if len(d) > 149 else ""})
    return res


def _ident(d, mfr, date, serial, part, plen, dram):
    yr, wk = d[date], d[date + 1]
    return {"manufacturer": jedec_name(d[mfr], d[mfr + 1]),
            "year": 2000 + _bcd(yr) if yr not in (0, 0xFF) else None,
            "week": _bcd(wk) if wk not in (0, 0xFF) else None,
            "serial": d[serial:serial + 4].hex().upper(),
            "part": _ascii(d[part:part + plen]),
            "dram_manufacturer": jedec_name(d[dram], d[dram + 1])}


def eeprom_paths() -> list[str]:
    paths = []
    for drv in ("ee1004", "spd5118", "at24"):
        for dev in glob(f"/sys/bus/i2c/drivers/{drv}/*-00*"):
            for name in ("eeprom",):
                p = f"{dev}/{name}"
                if read_bytes(p, 1) is not None or glob(p):
                    paths.append(p)
            # spd5118 exposes the EEPROM through nvmem
            for nv in glob(f"{dev}/*/nvmem") + glob(f"{dev}/nvmem*/nvmem"):
                paths.append(nv)
    return paths


def read_modules() -> list[dict]:
    """Decode every SPD EEPROM the current user can read."""
    out = []
    for p in eeprom_paths():
        data = read_bytes(p, 1024)
        if not data:
            continue
        dec = decode(data)
        if dec:
            dec["source"] = p
            dec["address"] = p.split("/")[-2]
            out.append(dec)
    return out
