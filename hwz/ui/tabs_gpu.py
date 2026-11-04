"""GPU-Z side: Graphics Card, Sensors and Advanced tabs."""

from __future__ import annotations

import csv
import os
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import report
from ..probes.sensors import unit_for
from ..sysfs import fmt_size
from .widgets import Badge, Banner, Field, Flag, Grid, Sparkline, key


def _mhz(v):
    return f"{v:.0f} MHz" if v else ""


class GraphicsTab(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        g = self.g = Grid("Graphics Card")
        g.row(("Name", 7))
        g.row(("GPU", 7))
        g.row(("Technology", 3), ("Revision", 2))
        g.row(("BIOS Version", 7))
        g.row(("Subvendor", 3), ("Device ID", 4))
        g.row(("Bus Interface", 9))
        g.row(("Shaders", 3), ("Rendering", 4))
        g.row(("Memory Type", 3), ("Bus Width", 4))
        g.row(("Memory Size", 3), ("Mem. Vendor", 4))
        g.row(("Kernel Driver", 9))
        g.row(("User Driver", 9))
        g.row(("GPU Clock", 2), ("Memory", 2), ("Boost", 2))
        g.row(("Base Clock", 2), ("Min~1", 2), ("Power Limit", 2))
        self.badge = Badge()
        g.place(self.badge, 0, 8, 4, 2, Qt.AlignmentFlag.AlignCenter)
        for c in range(1, 10):
            g.g.setColumnStretch(c, 1)
        v.addWidget(g)
        ap = Grid("Computing / Technologies", cols=1)
        w = QWidget()
        lay = QGridLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.flags = {}
        names = ["OpenCL", "CUDA", "Vulkan", "Ray Tracing", "OpenGL", "VA-API", "Vulkan Video", "GLES"]
        for i, n in enumerate(names):
            f = Flag(n)
            self.flags[n] = f
            lay.addWidget(f, i // 4, i % 4)
        ap.add_row_widget(w)
        v.addWidget(ap)
        self.status = QLabel("")
        self.status.setProperty("role", "muted")
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        v.addStretch(1)
        self.gpu = None

    def show_gpu(self, m, gi: int):
        if not m.gpus:
            self.g.set("Name", "No graphics adapter found")
            return
        g = self.gpu = m.gpus[gi]
        a = g.apis
        vk, gl, cl, va = a.get("vulkan", {}), a.get("opengl", {}), a.get("opencl", {}), a.get("vaapi", {})
        G = self.g
        G.set("Name", g.title)
        G.set("GPU", g.gpu)
        G.set("Technology", g.technology)
        G.set("Revision", g.revision)
        G.set("BIOS Version", g.vbios or ("part of the system firmware" if g.integrated else ""))
        G.set("Subvendor", g.subvendor or g.extra.get("subsystem", ""))
        G.set("Device ID", g.device_id)
        G.set("Bus Interface", g.bus)
        G.set("Shaders", g.shaders)
        apis = []
        if vk:
            apis.append(f"Vulkan {vk.get('api', '')}")
        if gl:
            apis.append(f"OpenGL {gl.get('core_version') or gl.get('major', '')}")
        G.set("Rendering", " / ".join(apis))
        G.set("Memory Type", g.memory_type)
        G.set("Bus Width", f"{g.bus_width} bit" if g.bus_width else "")
        G.set("Memory Size", fmt_size(g.memory_size) if g.memory_size else ("System" if g.integrated else ""))
        G.set("Mem. Vendor", g.memory_vendor)
        G.set("Kernel Driver", f"{g.driver}  {g.driver_version}")
        G.set("User Driver", vk.get("driver_info") or (gl.get("version") if gl else "") or
              ("detecting…" if not m.apis_ready else ""))
        G.set("Boost", _mhz(g.clk_boost))
        G.set("Base Clock", _mhz(g.clk_base))
        G.set("Min~1", _mhz(g.clk_min))
        G.set("Power Limit", f"{g.power_limit_w:.0f} W" if g.power_limit_w else "")
        self.badge.set(g.vendor, g.name.split()[0] if g.name else "")
        self.flags["OpenCL"].setChecked(bool(cl))
        self.flags["CUDA"].setChecked(bool(a.get("cuda")))
        self.flags["Vulkan"].setChecked(bool(vk))
        self.flags["Ray Tracing"].setChecked(bool(vk.get("ray_tracing")))
        self.flags["OpenGL"].setChecked(bool(gl) and not gl.get("gles"))
        self.flags["GLES"].setChecked(bool(gl) and bool(gl.get("gles")))
        self.flags["VA-API"].setChecked(bool(va.get("profiles")))
        self.flags["Vulkan Video"].setChecked(bool(vk.get("video_decode") or vk.get("video_encode")))
        if not m.apis_ready:
            self.status.setText("Detecting Vulkan, OpenGL, OpenCL and VA-API support…")
        elif m.apis.get("error"):
            self.status.setText(m.apis["error"])
        else:
            self.status.setText(f"PCI {g.dev.short_slot}   ·   {g.render or 'no render node'}")

    def tick(self, values: dict):
        self.g.set("GPU Clock", _mhz(values.get("GPU Clock")))
        mc = values.get("Memory Clock")
        self.g.set("Memory", _mhz(mc) if mc else ("shared" if self.gpu and self.gpu.integrated else ""))


class SensorRow:
    def __init__(self, grid: QGridLayout, r: int, name: str):
        self.name = name
        self.unit = unit_for(name)
        self.label = QLabel(name)
        self.value = Field(centered=False, width=104)
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.spark = Sparkline()
        if self.unit == "%":
            self.spark.vmax = 100.0
        grid.addWidget(self.label, r, 0)
        grid.addWidget(self.value, r, 1)
        grid.addWidget(self.spark, r, 2)
        self.vals: list[float] = []
        self.minv = self.maxv = None
        self.sum = 0.0
        self.n = 0

    def push(self, v: float, mode: str):
        self.spark.push(v)
        self.minv = v if self.minv is None else min(self.minv, v)
        self.maxv = v if self.maxv is None else max(self.maxv, v)
        self.sum += v
        self.n += 1
        self.show(v, mode)

    def show(self, cur, mode):
        v = {"Current": cur, "Minimum": self.minv, "Maximum": self.maxv,
             "Average": self.sum / self.n if self.n else None}[mode]
        if v is None:
            self.value.set("")
            return
        u = self.unit
        if self.name.startswith("Performance State"):
            txt = f"P{int(v)}"
        elif u in ("MHz", "RPM", "MB"):
            txt = f"{v:,.0f} {u}".replace(",", " ")
        elif u == "V":
            txt = f"{v:.3f} V"
        elif u in ("°C", "%", "W"):
            txt = f"{v:.1f} {u}"
        else:
            txt = f"{v:g}"
        self.value.set(txt)

    def reset(self):
        self.minv = self.maxv = None
        self.sum, self.n = 0.0, 0
        self.spark.clear()

    def widgets(self):
        return (self.label, self.value, self.spark)


class SensorsTab(QWidget):
    unlock = Signal()
    interval_changed = Signal(int)

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        bar = QHBoxLayout()
        bar.addWidget(key("Show"))
        self.mode = QComboBox()
        self.mode.addItems(["Current", "Minimum", "Maximum", "Average"])
        bar.addWidget(self.mode)
        bar.addWidget(key("Refresh"))
        self.rate = QComboBox()
        for ms, txt in ((500, "0.5 s"), (1000, "1 s"), (2000, "2 s"), (5000, "5 s")):
            self.rate.addItem(txt, ms)
        self.rate.setCurrentIndex(1)
        bar.addWidget(self.rate)
        self.reset_btn = QPushButton("Reset")
        bar.addWidget(self.reset_btn)
        bar.addStretch(1)
        self.log = QCheckBox("Log to file")
        bar.addWidget(self.log)
        v.addLayout(bar)
        self.banner = Banner("CPU power and core voltage need administrator rights (RAPL energy counters and MSRs "
                             "are root-only).", "Unlock…")
        self.banner.clicked.connect(self.unlock)
        v.addWidget(self.banner)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QWidget()
        self.grid = QGridLayout(self.inner)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(3)
        self.grid.setColumnStretch(2, 1)
        self.scroll.setWidget(self.inner)
        v.addWidget(self.scroll, 1)
        self.rows: dict[str, SensorRow] = {}
        self.headers: dict[str, QLabel] = {}
        self.order: list[tuple[str, str]] = []
        self.mode.currentTextChanged.connect(self._remode)
        self.reset_btn.clicked.connect(self._reset)
        self.log.toggled.connect(self._toggle_log)
        self.rate.currentIndexChanged.connect(lambda _: self.interval_changed.emit(self.rate.currentData()))
        self._logf = None
        self._logw = None
        self._log_cols: list[str] = []
        self._last: dict[str, float] = {}
        self.gpu_title = ""

    def set_gpu(self, title: str):
        if title != self.gpu_title:
            self.gpu_title = title
            self._rebuild()

    def _rebuild(self):
        for r in self.rows.values():
            for w in r.widgets():
                w.deleteLater()
        for h in self.headers.values():
            h.deleteLater()
        self.rows.clear()
        self.headers.clear()
        self.order.clear()

    def _ensure(self, group: str, name: str):
        key_ = f"{group}|{name}"
        if key_ in self.rows:
            return self.rows[key_]
        # append at the end of its group: rebuild positions
        self.order.append((group, name))
        groups = []
        for g, _ in self.order:
            if g not in groups:
                groups.append(g)
        r = 0
        for g in groups:
            if g not in self.headers:
                h = QLabel(f"<b>{g}</b>")
                self.headers[g] = h
            self.grid.addWidget(self.headers[g], r, 0, 1, 3)
            r += 1
            for gg, n in self.order:
                if gg != g:
                    continue
                k = f"{gg}|{n}"
                if k not in self.rows:
                    self.rows[k] = SensorRow(self.grid, r, n)
                else:
                    for c, w in enumerate(self.rows[k].widgets()):
                        self.grid.addWidget(w, r, c)
                r += 1
        self.grid.setRowStretch(r, 1)
        return self.rows[key_]

    def update_values(self, gpu_vals: dict, sys_vals: list[tuple[str, str, float]], admin_active: bool):
        self.banner.setVisible(not admin_active)
        mode = self.mode.currentText()
        items = [(f"GPU: {self.gpu_title}" if self.gpu_title else "GPU", k, float(v)) for k, v in gpu_vals.items()]
        items += [(g, n, float(v)) for g, n, v in sys_vals]
        for g, n, v in items:
            self._ensure(g, n).push(v, mode)
            self._last[f"{g}|{n}"] = v
        if self._logw:
            self._write_log()

    def _remode(self, mode):
        for k, r in self.rows.items():
            r.show(self._last.get(k), mode)

    def _reset(self):
        for r in self.rows.values():
            r.reset()

    def _toggle_log(self, on):
        if on:
            base = os.path.expanduser("~/linux-hw-z-sensors.csv")
            path, _ = QFileDialog.getSaveFileName(self, "Log sensors to", base, "CSV files (*.csv)")
            if not path:
                self.log.blockSignals(True)
                self.log.setChecked(False)
                self.log.blockSignals(False)
                return
            self._logf = open(path, "w", newline="", encoding="utf-8")
            self._logw = csv.writer(self._logf)
            self._log_cols = []
        else:
            if self._logf:
                self._logf.close()
            self._logf = self._logw = None

    def _write_log(self):
        keys = list(self._last.keys())
        if not self._log_cols:
            self._log_cols = keys
            self._logw.writerow(["time"] + [k.split("|", 1)[1] + (f" [{unit_for(k)}]" if unit_for(k) else "")
                                            for k in keys])
        self._logw.writerow([time.strftime("%Y-%m-%d %H:%M:%S")] +
                            [f"{self._last.get(k, ''):.3f}" if isinstance(self._last.get(k), float) else ""
                             for k in self._log_cols])
        self._logf.flush()

    def close_log(self):
        if self._logf:
            self._logf.close()
            self._logf = None


class AdvancedTab(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        top.addWidget(key("Show"))
        self.combo = QComboBox()
        self.combo.addItems(["General", "Vulkan", "OpenGL", "OpenCL", "VA-API (video)", "CPU flags",
                             "PCI devices", "Full report"])
        top.addWidget(self.combo, 1)
        v.addLayout(top)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Property", "Value"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setStretchLastSection(True)
        self.tree.setColumnWidth(0, 230)
        v.addWidget(self.tree, 1)
        self.combo.currentIndexChanged.connect(lambda _: self._show())
        self.m = None
        self.gi = 0

    def show_gpu(self, m, gi):
        self.m, self.gi = m, gi
        self._show()

    def _add(self, parent, k, v=""):
        it = QTreeWidgetItem([str(k), "" if v is None else str(v)])
        it.setToolTip(1, str(v) if v else "")
        (parent.addChild if isinstance(parent, QTreeWidgetItem) else self.tree.addTopLevelItem)(it)
        return it

    def _show(self):
        if not self.m:
            return
        t = self.tree
        t.clear()
        m = self.m
        g = m.gpus[self.gi] if m.gpus else None
        what = self.combo.currentText()
        apis = m.apis or {}
        if not m.apis_ready and what in ("Vulkan", "OpenGL", "OpenCL", "VA-API (video)"):
            self._add(t, "Detecting…", "the API probe is still running")
            return
        if what == "General" and not g:
            self._add(t, "No graphics adapter", "no PCI display controller was found (see Vulkan/OpenGL for "
                                                "software renderers)")
        if what == "General" and g:
            for k, v in report.gpu_rows(g):
                self._add(t, k, v)
            if g.extra.get("subsystem"):
                self._add(t, "Subsystem", g.extra["subsystem"])
            self._add(t, "Render node", g.render)
            self._add(t, "DRM card", g.card)
        elif what == "Vulkan":
            vk = apis.get("vulkan", {})
            if vk.get("error"):
                self._add(t, "Vulkan", vk["error"])
            self._add(t, "Instance version", vk.get("instance", ""))
            for d in vk.get("devices", []):
                it = self._add(t, d.get("name", "device"), d.get("type", ""))
                for k in ("api", "driver_name", "driver_info", "pci", "max_image_2d", "extensions"):
                    if d.get(k) not in (None, ""):
                        self._add(it, k.replace("_", " ").capitalize(), d[k])
                self._add(it, "Vendor / device ID", f"{d.get('vendor_id', 0):04X} / {d.get('device_id', 0):04X}")
                self._add(it, "Ray tracing", "Yes" if d.get("ray_tracing") else "No")
                if d.get("video_decode"):
                    self._add(it, "Video decode", ", ".join(x.replace("VK_KHR_video_decode_", "")
                                                            for x in d["video_decode"]))
                if d.get("video_encode"):
                    self._add(it, "Video encode", ", ".join(x.replace("VK_KHR_video_encode_", "")
                                                            for x in d["video_encode"]))
                for i, h in enumerate(d.get("heaps", [])):
                    self._add(it, f"Memory heap {i}", f"{fmt_size(h['size'])}"
                                                      f"{' (device local)' if h['device_local'] else ''}")
                it.setExpanded(True)
        elif what == "OpenGL":
            gl = apis.get("opengl", {})
            for k in ("vendor", "renderer", "version", "core_version", "glsl", "profile", "extensions", "platform",
                      "error"):
                if gl.get(k) not in (None, ""):
                    self._add(t, {"core_version": "Max core profile", "glsl": "GLSL version",
                                  "platform": "Qt platform"}.get(k, k.capitalize()), gl[k])
        elif what == "OpenCL":
            cl = apis.get("opencl", {})
            if cl.get("error"):
                self._add(t, "OpenCL", cl["error"])
            if not cl.get("platforms") and not cl.get("error"):
                self._add(t, "OpenCL", "no platforms (install an ICD, e.g. intel-opencl-icd / mesa-opencl-icd)")
            for p in cl.get("platforms", []):
                it = self._add(t, p.get("name") or "platform", p.get("version"))
                for d in p.get("devices", []):
                    di = self._add(it, d.get("name"), d.get("version"))
                    for k, lab in (("vendor", "Vendor"), ("driver", "Driver"), ("compute_units", "Compute units"),
                                   ("max_clock", "Max clock (MHz)"), ("pci", "PCI")):
                        if d.get(k):
                            self._add(di, lab, d[k])
                    if d.get("global_mem"):
                        self._add(di, "Global memory", fmt_size(d["global_mem"]))
                it.setExpanded(True)
        elif what == "VA-API (video)":
            va = apis.get("vaapi", {})
            if not va:
                self._add(t, "VA-API", "no render node / not probed")
            for node, info in va.items():
                it = self._add(t, node, info.get("driver") or info.get("error", ""))
                if info.get("version"):
                    self._add(it, "VA-API version", info["version"])
                for p in info.get("profiles", []):
                    self._add(it, p["profile"], ", ".join(p["entrypoints"]))
                it.setExpanded(True)
        elif what == "CPU flags":
            c = m.cpu
            self._add(t, "Instructions", ", ".join(c.instructions))
            it = self._add(t, "All /proc/cpuinfo flags", f"{len(c.flags)}")
            for i in range(0, len(c.flags), 8):
                self._add(it, "", " ".join(c.flags[i:i + 8]))
            it.setExpanded(True)
        elif what == "PCI devices":
            from ..probes import pci
            for d in pci.devices():
                it = self._add(t, d.short_slot, f"{d.vendor_name()} {d.device_name()}".strip() or
                               f"{d.vendor:04X}:{d.device:04X}")
                self._add(it, "Class", d.class_name())
                self._add(it, "IDs", f"{d.vendor:04X}:{d.device:04X}  sub {d.subvendor:04X}:{d.subdevice:04X}"
                                     f"  rev {d.revision:02X}")
                self._add(it, "Driver", d.driver or "")
                lk = d.link()
                if lk["max_gen"]:
                    self._add(it, "PCIe link", f"x{lk['cur_width']} {lk['cur_gen']} (max x{lk['max_width']} "
                                               f"{lk['max_gen']})")
        elif what == "Full report":
            for title, rows in report.sections(m):
                it = self._add(t, title)
                for k, v in rows:
                    self._add(it, k, v)
                it.setExpanded(True)
