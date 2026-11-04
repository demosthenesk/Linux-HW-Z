"""CPU / system sensors: clocks, utilisation, temperatures, fans, power, memory."""

from __future__ import annotations

import re
import time

from ..sysfs import glob, read, read_int
from . import cpu as cpumod
from . import memory

UNITS = [
    (r"Clock", "MHz"), (r"Power|Draw", "W"), (r"Voltage|VID", "V"), (r"RPM", "RPM"),
    (r"\(%\)|Load|Usage|Utili", "%"), (r"Temperature|Hot Spot|Tctl|Tccd|Composite", "°C"),
    (r"Memory Used|Used \(|Available", "MB"), (r"Performance State", ""),
]


def unit_for(name: str) -> str:
    for pat, u in UNITS:
        if re.search(pat, name):
            return u
    return ""


class SystemSampler:
    def __init__(self, info: cpumod.CPUInfo):
        self.info = info
        self._times = None
        self._hwmons = self._find_hwmons()

    @staticmethod
    def _find_hwmons() -> list[tuple[str, str]]:
        out = []
        for h in glob("/sys/class/hwmon/hwmon*"):
            name = read(f"{h}/name", "") or ""
            out.append((h, name))
        return out

    def sample(self, admin=None) -> list[tuple[str, str, float]]:
        """-> [(group, name, value)]"""
        res: list[tuple[str, str, float]] = []
        clocks = cpumod.current_mhz()
        if clocks:
            for g in self.info.groups:
                vals = [clocks[c] for c in g.cpus if c in clocks]
                if vals:
                    label = "CPU Clock" if g.name == "Cores" else f"CPU Clock ({g.name}, max)"
                    res.append(("CPU", label, max(vals)))
                    if g.name == "Cores" or len(self.info.groups) > 1:
                        res.append(("CPU", f"CPU Clock ({'avg' if g.name == 'Cores' else g.name + ', avg'})",
                                    sum(vals) / len(vals)))
        t = cpumod.cpu_times()
        if self._times:
            busy = tot = 0
            per = []
            for c, (b, tt) in t.items():
                pb, pt = self._times.get(c, (b, tt))
                db, dt = b - pb, tt - pt
                busy += db
                tot += dt
                if dt > 0:
                    per.append(db / dt * 100)
            if tot > 0:
                res.append(("CPU", "CPU Load", busy / tot * 100))
            if per:
                res.append(("CPU", "CPU Load (busiest thread)", max(per)))
        self._times = t
        for h, name in self._hwmons:
            res.extend(self._hwmon(h, name))
        if admin is not None and admin.active:
            vs = list(admin.vcore.values())
            if vs:
                res.append(("CPU", "Core Voltage (VID)", max(vs)))
            for key, w in sorted(admin.power.items()):
                zone = key.split("|", 1)[0]
                nice = {"package-0": "CPU Package Power", "package-1": "CPU Package Power (#2)", "core": "CPU Cores Power",
                        "uncore": "iGPU Power (uncore)", "dram": "DRAM Power", "psys": "Platform Power"}.get(zone,
                                                                                                         f"{zone} Power")
                res.append(("CPU", nice, w))
        mi = memory.meminfo()
        if mi.get("MemTotal"):
            used = mi["MemTotal"] - mi.get("MemAvailable", 0)
            res.append(("System", "System Memory Used", used / (1 << 20)))
            res.append(("System", "System Memory Usage (%)", used / mi["MemTotal"] * 100))
        return res

    def _hwmon(self, h: str, name: str) -> list[tuple[str, str, float]]:
        out = []
        if name in ("amdgpu", "i915", "xe", "nouveau", "nvidia"):
            return out  # reported with the GPU
        group = {"coretemp": "CPU", "k10temp": "CPU", "zenpower": "CPU", "nvme": "Storage",
                 "acpitz": "System", "drivetemp": "Storage"}.get(name, "System")
        for t in glob(f"{h}/temp*_input"):
            n = t.rsplit("/", 1)[1].split("_")[0]
            v = read_int(t)
            if v is None or v <= -40000 or v > 150000:
                continue
            label = read(f"{h}/{n}_label") or ""
            if name == "coretemp":
                if label.startswith("Package"):
                    label = "CPU Package Temperature"
                else:
                    label = label.replace("Core ", "Core ") + " Temperature"
            elif name in ("k10temp", "zenpower"):
                label = {"Tctl": "CPU Temperature (Tctl)", "Tdie": "CPU Temperature (Tdie)"}.get(
                    label, "CPU " + label.replace("Tccd", "CCD") + " Temperature")
            elif name == "nvme":
                label = f"NVMe {h.rsplit('hwmon', 1)[1]} {label or 'Temperature'}".replace("Composite", "Temperature")
            else:
                label = f"{name} {label or n} Temperature"
            out.append((group, label, v / 1000.0))
        for f in glob(f"{h}/fan*_input"):
            n = f.rsplit("/", 1)[1].split("_")[0]
            v = read_int(f)
            if v is None:
                continue
            label = read(f"{h}/{n}_label") or f"Fan {n[3:]}"
            out.append(("System", f"{label} Speed (RPM)" if "RPM" not in label else label, float(v)))
        if name in ("coretemp",):
            # keep only package + up to 16 cores to stay readable
            pk = [x for x in out if "Package" in x[1]]
            cores = [x for x in out if "Package" not in x[1]]
            if cores:
                out = pk + [("CPU", "CPU Core Temperature (max)", max(c[2] for c in cores))]
        return out
