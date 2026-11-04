"""Graphics adapters: identification and live clocks/sensors per vendor.

Sources: PCI sysfs + pci.ids, the DRM driver's sysfs (i915, xe, amdgpu,
nouveau), hwmon, NVML for the NVIDIA proprietary driver, and the per-process
DRM fdinfo statistics for engine utilisation on Intel.
"""

from __future__ import annotations

import os
import platform
import re
import time
from dataclasses import dataclass, field

from ..sysfs import exists, glob, link_name, listdir, read, read_int
from . import nvml, pci

GPU_CLASSES = (0x0300, 0x0302, 0x0380)

# Intel integrated / discrete graphics by device-ID prefix: (architecture, technology)
INTEL_ARCH = [
    (r"^01[0-6]", ("Gen6 (Sandy Bridge)", "32 nm")), (r"^015|^016", ("Gen7 (Ivy Bridge)", "22 nm")),
    (r"^04|^0A|^0D|^0C", ("Gen7.5 (Haswell)", "22 nm")), (r"^16|^22B", ("Gen8 (Broadwell)", "14 nm")),
    (r"^19", ("Gen9 (Skylake)", "14 nm")), (r"^59|^87C|^3E|^3EA|^9B", ("Gen9.5", "14 nm")),
    (r"^5A", ("Gen9.5 (Cannon Lake)", "10 nm")), (r"^8A", ("Gen11 (Ice Lake)", "10 nm")),
    (r"^4E|^4C|^9A|^490|^4F", ("Xe-LP (Gen12)", "10 nm SuperFin")),
    (r"^46", ("Xe-LP (Gen12.2)", "Intel 7")), (r"^A7", ("Xe-LP (Gen12.2)", "Intel 7")),
    (r"^56", ("Xe-HPG (Alchemist)", "TSMC N6")), (r"^7D", ("Xe-LPG (Gen12.7)", "Intel 4 / TSMC N5")),
    (r"^64", ("Xe2-LPG (Lunar Lake)", "TSMC N3B")), (r"^E2", ("Xe2-HPG (Battlemage)", "TSMC N5")),
    (r"^B0", ("Xe3-LPG (Panther Lake)", "TSMC N3E")),
]

CODENAME_TECH = [
    (r"^GB2", "TSMC 4NP"), (r"^AD1", "TSMC 4N"), (r"^GA10[02]", "TSMC 7 nm"), (r"^GA1", "Samsung 8 nm"),
    (r"^TU1", "TSMC 12 nm"), (r"^GP10[78]", "Samsung 14 nm"), (r"^GP1", "TSMC 16 nm"), (r"^GM", "TSMC 28 nm"),
    (r"^GK", "TSMC 28 nm"), (r"Navi 4", "TSMC N4P"), (r"Navi 33", "TSMC N6"), (r"Navi 3", "TSMC N5"),
    (r"Navi 2[34]", "TSMC N6"), (r"Navi 2", "TSMC N7"), (r"Navi 1", "TSMC N7"), (r"Vega 20", "TSMC N7"),
    (r"Vega|Polaris|Ellesmere|Baffin|Lexa", "GF 14 nm"), (r"Rembrandt", "TSMC N6"),
    (r"Phoenix|Hawk|Strix|Krackan", "TSMC N4"), (r"Renoir|Cezanne|Lucienne|Barcelo", "TSMC N7"),
    (r"Raphael|Granite", "TSMC N6"), (r"Raven|Picasso", "GF 14/12 nm"), (r"Van Gogh", "TSMC N7"),
    (r"Mendocino", "TSMC N6"),
]


MEM_TYPE = [
    (r"Navi [1-4]\d", "GDDR6"), (r"Vega 1[02]|Vega 20|Fiji", "HBM2"), (r"Polaris|Ellesmere|Baffin|Lexa|Hawaii|Tonga",
                                                                      "GDDR5"),
    (r"^GB20[2-7]", "GDDR7"), (r"^TU1", "GDDR6"), (r"^GP10[2-8]", "GDDR5/5X"), (r"^DG2|Alchemist|Battlemage", "GDDR6"),
]


@dataclass
class GpuInfo:
    index: int
    dev: pci.PciDev
    card: str = ""              # /sys/class/drm/cardN
    render: str = ""            # /dev/dri/renderD128
    vendor: str = ""
    name: str = ""
    gpu: str = ""
    technology: str = ""
    revision: str = ""
    subvendor: str = ""
    device_id: str = ""
    bus: str = ""
    integrated: bool = False
    driver: str = ""
    driver_version: str = ""
    vbios: str = ""
    memory_size: int | None = None      # bytes of dedicated VRAM
    memory_type: str = ""
    memory_vendor: str = ""
    bus_width: int | None = None
    shaders: str = ""
    clk_base: float | None = None
    clk_boost: float | None = None
    clk_min: float | None = None
    mem_clk_max: float | None = None
    power_limit_w: float | None = None
    apis: dict = field(default_factory=dict)   # filled from the API probe subprocess
    extra: dict = field(default_factory=dict)

    @property
    def title(self) -> str:
        return f"{self.vendor} {self.name}".strip()


def _intel_arch(dev_id: int):
    h = f"{dev_id:04X}"
    for pat, val in INTEL_ARCH:
        if re.match(pat, h):
            return val
    return ("", "")


def _tech_for(code: str) -> str:
    for pat, tech in CODENAME_TECH:
        if re.search(pat, code):
            return tech
    return ""


def _drm_card(dev: pci.PciDev) -> tuple[str, str]:
    card = render = ""
    for n in listdir(f"{dev.path}/drm"):
        if re.fullmatch(r"card\d+", n):
            card = f"/sys/class/drm/{n}"
        elif n.startswith("renderD"):
            render = f"/dev/dri/{n}"
    return card, render


def _hwmon(dev: pci.PciDev) -> str:
    hs = glob(f"{dev.path}/hwmon/hwmon*")
    return hs[0] if hs else ""


def _mhz_list(text: str | None):
    """amdgpu pp_dpm_* -> (levels in MHz, active MHz)."""
    levels, cur = [], None
    for line in (text or "").splitlines():
        m = re.search(r"(\d+)\s*Mhz(\s*\*)?", line, re.I)
        if m:
            v = float(m.group(1))
            levels.append(v)
            if m.group(2):
                cur = v
    return levels, cur


def probe() -> list[GpuInfo]:
    gpus: list[GpuInfo] = []
    devs = [d for d in pci.devices() if (d.cls >> 8) in GPU_CLASSES]
    # boot VGA first, then by slot
    devs.sort(key=lambda d: (read(f"{d.path}/boot_vga", "0") != "1", d.slot))
    for i, d in enumerate(devs):
        g = GpuInfo(index=i, dev=d)
        g.card, g.render = _drm_card(d)
        g.vendor = pci.short_vendor(d.vendor)
        full = d.device_name() or f"Device {d.device:04X}"
        code, name = pci.split_name(full)
        g.gpu, g.name = code, name
        g.revision = f"{d.revision:02X}"
        g.subvendor = pci.short_vendor(d.subvendor) if d.subvendor else ""
        sub = d.subsys_name()
        if sub:
            g.extra["subsystem"] = sub
        g.device_id = f"{d.vendor:04X} {d.device:04X} - {d.subvendor:04X} {d.subdevice:04X}"
        g.driver = d.driver or "none"
        lk = d.link()
        root = d.slot.startswith("0000:00:")
        g.integrated = (d.vendor == 0x8086 and root) or (d.vendor == 0x1002 and _amd_apu(d)) or \
            (d.vendor not in (0x10DE,) and root)
        if lk["max_gen"] and not g.integrated:
            g.bus = f"PCIe x{lk['max_width']} {lk['max_gen']} @ x{lk['cur_width']} {lk['cur_gen']}"
        elif g.integrated:
            g.bus = "Integrated (on-die)"
        else:
            g.bus = "PCI"
        if d.vendor == 0x8086:
            arch, tech = _intel_arch(d.device)
            if arch:
                g.gpu = f"{code} ({arch})" if code else arch
            g.technology = tech
        else:
            g.technology = _tech_for(code or name)
        if not g.integrated:
            for pat, mt in MEM_TYPE:
                if re.search(pat, f"{code} {g.gpu}"):
                    g.memory_type = mt
                    break
        kver = platform.release()
        g.driver_version = read(f"/sys/module/{g.driver}/version", "") or f"in-kernel ({kver})"
        try:
            _vendor_static(g)
        except Exception as e:  # never let one adapter break the whole probe
            g.extra["error"] = str(e)
        gpus.append(g)
    return gpus


APU_NAMES = re.compile(r"Renoir|Cezanne|Lucienne|Barcelo|Rembrandt|Phoenix|Hawk Point|Raphael|Granite Ridge|"
                       r"Dragon Range|Picasso|Raven|Mendocino|Van Gogh|Strix|Krackan|Stoney|Carrizo|Bristol|"
                       r"Kaveri|Godavari|Mullins|Kabini|Wrestler|Trinity|Richland|Sumo|Beavercreek|Radeon Vega Mobile",
                       re.I)


def _amd_apu(d: pci.PciDev) -> bool:
    if APU_NAMES.search(d.device_name() or ""):
        return True
    tot = read_int(f"{d.path}/mem_info_vram_total")
    return tot is not None and tot <= 2 << 30 and read_int(f"{d.path}/mem_info_vis_vram_total", 0) == tot \
        and not d.link().get("max_gen")


def _vendor_static(g: GpuInfo):
    p = g.dev.path
    if g.driver == "i915" and g.card:
        g.clk_boost = read_int(f"{g.card}/gt_RP0_freq_mhz") or read_int(f"{g.card}/gt_max_freq_mhz")
        g.clk_base = read_int(f"{g.card}/gt_RP1_freq_mhz")
        g.clk_min = read_int(f"{g.card}/gt_RPn_freq_mhz")
        if g.integrated:
            g.memory_type = "Shared (system RAM)"
    elif g.driver == "xe":
        f = _xe_freq_dir(p)
        if f:
            g.clk_boost = read_int(f"{f}/rp0_freq") or read_int(f"{f}/max_freq")
            g.clk_base = read_int(f"{f}/rpe_freq")
            g.clk_min = read_int(f"{f}/rpn_freq")
        if g.integrated:
            g.memory_type = "Shared (system RAM)"
    elif g.driver == "amdgpu":
        g.vbios = read(f"{p}/vbios_version", "") or ""
        g.memory_size = read_int(f"{p}/mem_info_vram_total")
        g.memory_vendor = (read(f"{p}/mem_info_vram_vendor", "") or "").capitalize()
        lv, _ = _mhz_list(read(f"{p}/pp_dpm_sclk"))
        if lv:
            g.clk_boost, g.clk_min = max(lv), min(lv)
        ml, _ = _mhz_list(read(f"{p}/pp_dpm_mclk"))
        if ml:
            g.mem_clk_max = max(ml)
        h = _hwmon(g.dev)
        cap = read_int(f"{h}/power1_cap") if h else None
        if cap:
            g.power_limit_w = cap / 1e6
        if g.integrated:
            g.memory_type = "Shared (system RAM)"
    elif g.driver == "nvidia":
        n = nvml.static(g.dev.slot)
        if n:
            g.name = re.sub(r"^NVIDIA\s+", "", n.get("name") or "") or g.name
            g.vbios = n.get("vbios", "")
            g.driver_version = n.get("driver", g.driver_version)
            g.memory_size = n.get("mem_total")
            g.bus_width = n.get("bus_width")
            if n.get("cores"):
                g.shaders = f"{n['cores']} Unified"
            g.clk_boost = n.get("max_gfx")
            g.mem_clk_max = n.get("max_mem")
            g.power_limit_w = n.get("power_limit_w")
            if n.get("pcie_max_gen"):
                g.bus = (f"PCIe x{n['pcie_max_width']} {n['pcie_max_gen']}.0 @ "
                         f"x{n['pcie_cur_width']} {n['pcie_cur_gen']}.0")
            g.extra["nvml"] = True
    elif g.driver == "nouveau":
        g.memory_size = None


def _xe_freq_dir(p: str) -> str:
    hits = glob(f"{p}/tile0/gt0/freq0")
    return hits[0] if hits else ""


class GpuSampler:
    """Reads live values for one GPU.  Call sample() about once per second."""

    def __init__(self, g: GpuInfo):
        self.g = g
        self.hw = _hwmon(g.dev)
        self._energy = None   # (t, joules) for energy-counter based power
        self._fd_prev = None  # (t, {engine: ns or cycles})

    def sample(self) -> dict[str, float | None]:
        g, p, out = self.g, self.g.dev.path, {}
        try:
            if g.driver == "i915" and g.card:
                out["GPU Clock"] = read_int(f"{g.card}/gt_act_freq_mhz") or read_int(f"{g.card}/gt_cur_freq_mhz")
                out["GPU Clock (requested)"] = read_int(f"{g.card}/gt_cur_freq_mhz")
                rc6 = read_int(f"{g.card}/power/rc6_residency_ms")
                if rc6 is not None:
                    out["_rc6"] = rc6
                out.update(self._fdinfo())
            elif g.driver == "xe":
                f = _xe_freq_dir(p)
                if f:
                    out["GPU Clock"] = read_int(f"{f}/act_freq")
                    out["GPU Clock (requested)"] = read_int(f"{f}/cur_freq")
                out.update(self._fdinfo())
            elif g.driver == "amdgpu":
                _, cur = _mhz_list(read(f"{p}/pp_dpm_sclk"))
                _, mcur = _mhz_list(read(f"{p}/pp_dpm_mclk"))
                if self.hw:
                    f1 = read_int(f"{self.hw}/freq1_input")
                    f2 = read_int(f"{self.hw}/freq2_input")
                    cur = f1 / 1e6 if f1 else cur
                    mcur = f2 / 1e6 if f2 else mcur
                out["GPU Clock"] = cur
                out["Memory Clock"] = mcur
                out["GPU Load"] = read_int(f"{p}/gpu_busy_percent")
                out["Memory Controller Load"] = read_int(f"{p}/mem_busy_percent")
                used = read_int(f"{p}/mem_info_vram_used")
                out["Memory Used (Dedicated)"] = used / (1 << 20) if used is not None else None
                gtt = read_int(f"{p}/mem_info_gtt_used")
                out["Memory Used (Dynamic)"] = gtt / (1 << 20) if gtt is not None else None
            elif g.driver == "nvidia" and g.extra.get("nvml"):
                out.update(nvml.sample(g.dev.slot))
            if self.hw and g.driver != "nvidia":
                out.update(self._hwmon_values())
        except Exception:
            pass
        return {k: v for k, v in out.items() if v is not None and not k.startswith("_")}

    def _hwmon_values(self) -> dict:
        h, out = self.hw, {}
        for t in glob(f"{h}/temp*_input"):
            n = t.rsplit("/", 1)[1].split("_")[0]
            label = read(f"{h}/{n}_label") or ""
            v = read_int(t)
            if v is None:
                continue
            nice = {"edge": "GPU Temperature", "junction": "Hot Spot", "mem": "Memory Temperature",
                    "pkg": "GPU Temperature", "vram": "Memory Temperature"}.get(label.lower(), "")
            out[nice or f"Temperature ({label or n})"] = v / 1000.0
        f = read_int(f"{h}/fan1_input")
        if f is not None:
            out["Fan Speed (RPM)"] = f
        pwm = read_int(f"{h}/pwm1")
        if pwm is not None:
            out["Fan Speed (%)"] = pwm * 100 / 255
        pw = read_int(f"{h}/power1_average") or read_int(f"{h}/power1_input")
        if pw:
            out["Board Power Draw"] = pw / 1e6
        else:
            e = read_int(f"{h}/energy1_input")
            if e is not None:
                now = time.monotonic()
                if self._energy:
                    dt = now - self._energy[0]
                    if dt > 0:
                        out["Board Power Draw"] = (e - self._energy[1]) / 1e6 / dt
                self._energy = (now, e)
        v = read_int(f"{h}/in0_input")
        if v is not None:
            out["GPU Voltage"] = v / 1000.0
        return out

    def _fdinfo(self) -> dict:
        """Engine busy % from DRM fdinfo of the processes this user can see."""
        slot = self.g.dev.slot
        clients: dict[str, dict[str, int]] = {}
        totals_xe: dict[str, int] = {}
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            fdd = f"/proc/{pid}/fd"
            try:
                fds = os.listdir(fdd)
            except OSError:
                continue
            for fd in fds:
                try:
                    if not os.readlink(f"{fdd}/{fd}").startswith("/dev/dri/"):
                        continue
                    with open(f"/proc/{pid}/fdinfo/{fd}") as fh:
                        txt = fh.read()
                except OSError:
                    continue
                if f"drm-pdev:\t{slot}" not in txt and f"drm-pdev: {slot}" not in txt:
                    continue
                cid = re.search(r"drm-client-id:\s*(\d+)", txt)
                key = cid.group(1) if cid else f"{pid}/{fd}"
                eng = {}
                for m in re.finditer(r"drm-engine-([\w-]+):\s*(\d+)\s*ns", txt):
                    eng[m.group(1)] = int(m.group(2))
                for m in re.finditer(r"drm-cycles-(\w+):\s*(\d+)", txt):
                    eng["c:" + m.group(1)] = int(m.group(2))
                for m in re.finditer(r"drm-total-cycles-(\w+):\s*(\d+)", txt):
                    totals_xe[m.group(1)] = max(totals_xe.get(m.group(1), 0), int(m.group(2)))
                clients[key] = eng
        agg: dict[str, int] = {}
        for eng in clients.values():
            for k, v in eng.items():
                agg[k] = agg.get(k, 0) + v
        for k, v in totals_xe.items():
            agg["t:" + k] = v
        now = time.monotonic()
        out = {}
        if self._fd_prev:
            t0, prev = self._fd_prev
            dt_ns = (now - t0) * 1e9
            busy = {}
            for k, v in agg.items():
                if k.startswith(("c:", "t:")):
                    continue
                d = v - prev.get(k, v)
                busy[k] = max(0.0, min(100.0, d / dt_ns * 100)) if dt_ns > 0 else 0.0
            for k, v in agg.items():
                if k.startswith("c:"):
                    cls = k[2:]
                    dc = v - prev.get(k, v)
                    dt = agg.get("t:" + cls, 0) - prev.get("t:" + cls, agg.get("t:" + cls, 0))
                    if dt > 0:
                        busy[cls] = max(0.0, min(100.0, dc / dt * 100))
            render = max([busy.get(x, 0.0) for x in ("render", "rcs", "compute", "ccs")] or [0.0])
            video = max([busy.get(x, 0.0) for x in ("video", "vcs", "video-enhance", "vecs")] or [0.0])
            out["GPU Load"] = max(busy.values()) if busy else 0.0
            out["Render Engine Load"] = render
            out["Video Engine Load"] = video
        self._fd_prev = (now, agg)
        return out
