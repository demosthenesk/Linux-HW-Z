"""Processor information: identification, clocks, caches, topology."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .. import native
from ..sysfs import exists, glob, listdir, parse_cpulist, read, read_int
from . import codenames

CPU = "/sys/devices/system/cpu"

INSTR_MAP = [  # (cpuinfo flag, CPU-Z style name)
    ("mmx", "MMX"), ("3dnowext", "3DNow!+"), ("3dnow", "3DNow!"), ("sse", "SSE"), ("sse2", "SSE2"),
    ("pni", "SSE3"), ("ssse3", "SSSE3"), ("sse4_1", "SSE4.1"), ("sse4_2", "SSE4.2"), ("sse4a", "SSE4A"),
    ("lm", "x86-64"), ("vmx", "VT-x"), ("svm", "AMD-V"), ("aes", "AES"), ("avx", "AVX"),
    ("avx2", "AVX2"), ("avx_vnni", "AVX-VNNI"), ("avx512f", "AVX-512F"), ("avx512bw", "AVX-512BW"),
    ("avx512vl", "AVX-512VL"), ("avx512_vnni", "AVX-512VNNI"), ("avx512_bf16", "AVX-512BF16"),
    ("avx10", "AVX10"), ("fma", "FMA3"), ("fma4", "FMA4"), ("sha_ni", "SHA"), ("amx_tile", "AMX"),
    ("rdrand", "RDRAND"), ("bmi2", "BMI2"),
]


@dataclass
class CacheLine:
    level: int
    kind: str            # Data / Instruction / Unified
    size_kb: int
    ways: int | None
    line: int | None
    count: int
    shared_by: int       # logical CPUs per instance

    @property
    def label(self) -> str:
        if self.level == 1:
            return "L1 Data" if self.kind == "Data" else "L1 Inst." if self.kind == "Instruction" else "Level 1"
        return f"Level {self.level}"

    def size_text(self) -> str:
        if self.size_kb >= 1024 and self.size_kb % 1024 == 0:
            return f"{self.size_kb // 1024} MBytes"
        return f"{self.size_kb} KBytes"

    def text(self) -> str:
        return f"{self.count} x {self.size_text()}" if self.count > 1 else self.size_text()

    def ways_text(self) -> str:
        return f"{self.ways}-way" if self.ways else ""


@dataclass
class CoreGroup:
    name: str                      # "P-Core", "E-Core" or "Cores"
    cpus: list[int]
    cores: int
    max_mhz: float | None = None
    base_mhz: float | None = None
    min_mhz: float | None = None
    caches: list[CacheLine] = field(default_factory=list)


@dataclass
class CPUInfo:
    vendor: str = ""
    vendor_short: str = ""
    brand: str = ""
    name: str = ""
    codename: str = ""
    technology: str = ""
    family: int = 0
    model: int = 0
    stepping: int = 0
    base_family: int = 0
    base_model: int = 0
    ext_family: int = 0
    ext_model: int = 0
    microcode: str = ""
    instructions: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    sockets: int = 1
    cores: int = 0
    threads: int = 0
    groups: list[CoreGroup] = field(default_factory=list)
    bus_mhz: float = 100.0
    tdp_w: float | None = None
    scaling_driver: str = ""
    governor: str = ""
    hypervisor: str = ""
    bogomips: str = ""
    address_sizes: str = ""
    package: str = ""          # filled by DMI (admin) when available
    core_voltage: str = ""     # filled by admin helper
    max_turbo_mhz: float | None = None
    all_caches: list = field(default_factory=list)


def _cpuinfo() -> list[dict[str, str]]:
    procs, cur = [], {}
    text = read("/proc/cpuinfo", "") or ""
    for line in text.splitlines():
        if not line.strip():
            if cur:
                procs.append(cur)
                cur = {}
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            cur[k.strip()] = v.strip()
    if cur:
        procs.append(cur)
    return procs


def online_cpus() -> list[int]:
    cpus = parse_cpulist(read(f"{CPU}/online"))
    if not cpus:
        cpus = sorted(int(m.group(1)) for d in listdir(CPU) if (m := re.fullmatch(r"cpu(\d+)", d)))
    return cpus


def short_name(brand: str) -> str:
    s = re.sub(r"\((R|TM|tm|r)\)", "", brand)
    s = re.sub(r"\b\d+(th|st|nd|rd) Gen\b", "", s)
    s = re.sub(r"\s*@.*$", "", s)
    s = re.sub(r"\b(CPU|Processor|\d+-Core)\b", "", s)
    s = re.sub(r"\bwith Radeon.*$", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("Core i", "Core i").replace(" -", "-")
    return s


def _caches_for(cpus: list[int]) -> list[CacheLine]:
    instances: dict[tuple, dict] = {}
    for c in cpus:
        base = f"{CPU}/cpu{c}/cache"
        for idx in listdir(base):
            if not idx.startswith("index"):
                continue
            d = f"{base}/{idx}"
            level = read_int(f"{d}/level")
            kind = read(f"{d}/type", "Unified")
            size = read(f"{d}/size", "")
            shared = read(f"{d}/shared_cpu_list", str(c))
            if level is None or not size:
                continue
            m = re.match(r"(\d+)\s*([KMG]?)", size)
            if not m:
                continue
            kb = int(m.group(1)) * {"": 1 / 1024, "K": 1, "M": 1024, "G": 1 << 20}[m.group(2)]
            key = (level, kind, shared)
            instances[key] = dict(level=level, kind=kind, kb=int(kb), ways=read_int(f"{d}/ways_of_associativity"),
                                  line=read_int(f"{d}/coherency_line_size"),
                                  shared_by=len(parse_cpulist(shared)) or 1)
    groups: dict[tuple, CacheLine] = {}
    for inst in instances.values():
        key = (inst["level"], inst["kind"], inst["kb"], inst["ways"])
        if key in groups:
            groups[key].count += 1
        else:
            groups[key] = CacheLine(inst["level"], inst["kind"], inst["kb"], inst["ways"], inst["line"], 1,
                                    inst["shared_by"])
    order = {"Data": 0, "Instruction": 1, "Unified": 2}
    return sorted(groups.values(), key=lambda c: (c.level, order.get(c.kind, 3), -c.size_kb))


def merge_caches(lines: list[CacheLine]) -> dict[str, tuple[str, str]]:
    """label -> (size text, ways text), joining hybrid groups with ' + '."""
    out: dict[str, list[CacheLine]] = {}
    for cl in lines:
        out.setdefault(cl.label, []).append(cl)
    res = {}
    for label, cls in out.items():
        res[label] = (" + ".join(c.text() for c in cls), " + ".join(c.ways_text() for c in cls if c.ways_text()))
    return res


def _khz(path: str) -> float | None:
    v = read_int(path)
    return v / 1000.0 if v else None


def _group(name: str, cpus: list[int], core_of: dict[int, tuple]) -> CoreGroup:
    g = CoreGroup(name=name, cpus=cpus, cores=len({core_of.get(c, (0, c)) for c in cpus}))
    maxes = [m for c in cpus if (m := _khz(f"{CPU}/cpu{c}/cpufreq/cpuinfo_max_freq"))]
    mins = [m for c in cpus if (m := _khz(f"{CPU}/cpu{c}/cpufreq/cpuinfo_min_freq"))]
    bases = [m for c in cpus if (m := _khz(f"{CPU}/cpu{c}/cpufreq/base_frequency"))]
    if not bases:
        bases = [m for c in cpus if (m := _khz(f"{CPU}/cpu{c}/cpufreq/amd_pstate_nominal_freq"))]
    g.max_mhz = max(maxes) if maxes else None
    g.min_mhz = min(mins) if mins else None
    g.base_mhz = max(bases) if bases else None
    g.caches = _caches_for(cpus)
    return g


def probe() -> CPUInfo:
    info = CPUInfo()
    procs = _cpuinfo()
    p0 = procs[0] if procs else {}
    info.vendor = p0.get("vendor_id", "")
    info.brand = re.sub(r"\s+", " ", p0.get("model name", "")).strip()
    info.flags = p0.get("flags", "").split()
    info.microcode = p0.get("microcode", "")
    info.bogomips = p0.get("bogomips", "")
    info.address_sizes = p0.get("address sizes", "")

    regs = None if os.environ.get("HWZ_ROOT") else native.cpuid(1)
    if regs:
        eax = regs[0]
        info.stepping = eax & 0xF
        info.base_model = (eax >> 4) & 0xF
        info.base_family = (eax >> 8) & 0xF
        info.ext_model = (eax >> 16) & 0xF
        info.ext_family = (eax >> 20) & 0xFF
        info.family = info.base_family + (info.ext_family if info.base_family == 0xF else 0)
        info.model = info.base_model | (info.ext_model << 4) if info.base_family in (6, 0xF) else info.base_model
    else:
        info.family = int(p0.get("cpu family", "0") or 0)
        info.model = int(p0.get("model", "0") or 0)
        info.stepping = int(p0.get("stepping", "0") or 0) if p0.get("stepping", "").isdigit() else 0
        info.base_family = min(info.family, 0xF)
        info.ext_family = info.family - 0xF if info.family > 0xF else 0
        info.base_model = info.model & 0xF
        info.ext_model = info.model >> 4
    # brand string straight from CPUID when /proc lacks it
    if not info.brand and not os.environ.get("HWZ_ROOT"):
        parts = []
        for leaf in (0x80000002, 0x80000003, 0x80000004):
            r = native.cpuid(leaf)
            if r:
                parts.append(b"".join(x.to_bytes(4, "little") for x in r))
        info.brand = b"".join(parts).decode("ascii", "ignore").strip("\x00 ")

    info.vendor_short = {"GenuineIntel": "Intel", "AuthenticAMD": "AMD", "HygonGenuine": "Hygon",
                         "CentaurHauls": "VIA", "  Shanghai  ": "Zhaoxin"}.get(info.vendor, info.vendor)
    info.name = short_name(info.brand)
    info.codename, info.technology = codenames.lookup(info.vendor, info.family, info.model, info.stepping)
    fl = set(info.flags)
    info.instructions = [name for flag, name in INSTR_MAP if flag in fl]
    if "hypervisor" in fl:
        info.hypervisor = "yes"

    cpus = online_cpus()
    info.threads = len(cpus)
    core_of: dict[int, tuple] = {}
    pkgs = set()
    for c in cpus:
        pk = read_int(f"{CPU}/cpu{c}/topology/physical_package_id", 0)
        co = read_int(f"{CPU}/cpu{c}/topology/core_id", c)
        core_of[c] = (pk, co)
        pkgs.add(pk)
    info.sockets = max(1, len(pkgs))
    info.cores = len(set(core_of.values())) or info.threads

    pcores = parse_cpulist(read("/sys/devices/cpu_core/cpus"))
    ecores = parse_cpulist(read("/sys/devices/cpu_atom/cpus"))
    if pcores and ecores:
        info.groups = [_group("P-Core", [c for c in pcores if c in cpus], core_of),
                       _group("E-Core", [c for c in ecores if c in cpus], core_of)]
    else:
        info.groups = [_group("Cores", cpus, core_of)]
    info.all_caches = _caches_for(cpus)
    maxes = [g.max_mhz for g in info.groups if g.max_mhz]
    info.max_turbo_mhz = max(maxes) if maxes else None

    info.scaling_driver = read(f"{CPU}/cpu0/cpufreq/scaling_driver", "") or ""
    info.governor = read(f"{CPU}/cpu0/cpufreq/scaling_governor", "") or ""

    # TDP: RAPL package limit (readable by users; the energy counter usually is not)
    for d in glob("/sys/class/powercap/intel-rapl:*"):
        if ":" in d.rsplit("intel-rapl:", 1)[1]:
            continue  # sub-zones
        if (read(f"{d}/name") or "").startswith("package"):
            uw = read_int(f"{d}/constraint_0_max_power_uw") or read_int(f"{d}/constraint_0_power_limit_uw")
            if uw:
                info.tdp_w = uw / 1e6
            break
    return info


def current_mhz() -> dict[int, float]:
    """Per-CPU current clock (MHz)."""
    out = {}
    for c in online_cpus():
        v = read_int(f"{CPU}/cpu{c}/cpufreq/scaling_cur_freq")
        if v:
            out[c] = v / 1000.0
    if not out:
        for i, p in enumerate(_cpuinfo()):
            try:
                out[int(p.get("processor", i))] = float(p.get("cpu MHz", "0"))
            except ValueError:
                pass
    return out


def cpu_times() -> dict[int, tuple[int, int]]:
    """Per-CPU (busy, total) jiffies from /proc/stat, for utilisation."""
    out = {}
    for line in (read("/proc/stat", "") or "").splitlines():
        if line.startswith("cpu") and line[3:4].isdigit():
            parts = line.split()
            vals = [int(x) for x in parts[1:]]
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
            total = sum(vals[:8])
            out[int(parts[0][3:])] = (total - idle, total)
    return out
