"""System memory: usage from /proc/meminfo, type/slots from SMBIOS, timings from SPD."""

from __future__ import annotations

from ..sysfs import read
from . import dmi


def meminfo() -> dict[str, int]:
    out = {}
    for line in (read("/proc/meminfo", "") or "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            try:
                out[k.strip()] = int(v.split()[0]) * 1024
            except (ValueError, IndexError):
                pass
    return out


def summary(smbios: dict | None, spd_modules: list[dict]) -> dict:
    mi = meminfo()
    res = {"total": mi.get("MemTotal"), "available": mi.get("MemAvailable"),
           "swap_total": mi.get("SwapTotal"), "swap_free": mi.get("SwapFree"),
           "type": "", "installed_mb": None, "channels": "", "speed": None, "configured_speed": None,
           "slots_used": None, "slots_total": None, "max_capacity_kb": None, "modules": [], "timings": None}
    mods = (smbios or {}).get("memory", [])
    if mods:
        pop = [m for m in mods if m["size_mb"]]
        res["modules"] = mods
        res["slots_total"] = len(mods)
        res["slots_used"] = len(pop)
        res["installed_mb"] = sum(m["size_mb"] for m in pop) or None
        types = {m["type"] for m in pop if m["type"]}
        res["type"] = " / ".join(sorted(types))
        res["channels"] = dmi.channels(mods)
        sp = [m["speed"] for m in pop if m["speed"]]
        cs = [m["configured_speed"] for m in pop if m["configured_speed"]]
        res["speed"] = max(sp) if sp else None
        res["configured_speed"] = max(cs) if cs else res["speed"]
        arr = (smbios or {}).get("arrays", [])
        sys_arrays = [a for a in arr if a.get("use") in (3, 0)] or arr
        if sys_arrays:
            res["max_capacity_kb"] = sum(a["max_kb"] or 0 for a in sys_arrays) or None
    if spd_modules:
        m0 = spd_modules[0]
        if not res["type"]:
            res["type"] = m0.get("type", "")
        if res["installed_mb"] is None:
            res["installed_mb"] = sum(m.get("size_mb", 0) for m in spd_modules) or None
        # timings for the configured speed: pick the JEDEC row closest to it
        target = (res["configured_speed"] or 0) / 2
        rows = m0.get("timings") or []
        if rows:
            best = min(rows, key=lambda r: abs(r["freq"] - target)) if target else rows[-1]
            res["timings"] = best
    return res
