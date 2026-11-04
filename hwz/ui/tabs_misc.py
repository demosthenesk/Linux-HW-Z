"""Bench and About tabs."""

from __future__ import annotations

import os
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, __version__, bench
from .widgets import Field, Grid, key


class ScoreBar(QProgressBar):
    def __init__(self, ref=False):
        super().__init__()
        self.setRange(0, 1000)
        self.setTextVisible(True)
        self.setFormat("")
        self.setFixedHeight(20)
        if ref:
            self.setProperty("ref", True)

    def show_score(self, score: float, scale: float):
        self.setValue(int(min(1.0, score / scale) * 1000) if scale > 0 else 0)
        self.setFormat(f"{score:.1f}" if score else "")


class BenchTab(QWidget):
    status = Signal(str)

    def __init__(self):
        super().__init__()
        self.runner = bench.Runner()
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(8)
        st = Grid("CPU Single Thread", cols=3)
        self.st_this, self.st_ref = ScoreBar(), ScoreBar(ref=True)
        st.place(key("This Processor"), 0, 0)
        st.place(self.st_this, 0, 1, 1, 2)
        self.st_ref_label = key("Reference")
        st.place(self.st_ref_label, 1, 0)
        st.place(self.st_ref, 1, 1, 1, 2)
        st.g.setColumnStretch(1, 1)
        v.addWidget(st)
        mt = Grid("CPU Multi Thread", cols=3)
        self.mt_this, self.mt_ref = ScoreBar(), ScoreBar(ref=True)
        mt.place(key("This Processor"), 0, 0)
        mt.place(self.mt_this, 0, 1, 1, 2)
        mt.place(key("Reference"), 1, 0)
        mt.place(self.mt_ref, 1, 1, 1, 2)
        row = QHBoxLayout()
        row.addWidget(key("Number of Threads"))
        self.threads = QSpinBox()
        self.threads.setRange(1, max(1, os.cpu_count() or 1))
        self.threads.setValue(os.cpu_count() or 1)
        row.addWidget(self.threads)
        row.addSpacing(16)
        row.addWidget(key("Multi Thread Ratio"))
        self.ratio = Field(centered=True, width=70)
        row.addWidget(self.ratio)
        row.addStretch(1)
        w = QWidget()
        w.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        mt.place(w, 2, 0, 1, 3)
        mt.g.setColumnStretch(1, 1)
        v.addWidget(mt)

        opt = Grid("Options", cols=4)
        opt.place(key("Reference"), 0, 0)
        self.ref = QComboBox()
        opt.place(self.ref, 0, 1, 1, 3)
        opt.place(key("Duration"), 1, 0)
        self.dur = QComboBox()
        for s in (4, 10, 30):
            self.dur.addItem(f"{s} s per test", s)
        opt.place(self.dur, 1, 1)
        opt.place(key("This Processor"), 2, 0)
        self.cpu_name = Field()
        opt.place(self.cpu_name, 2, 1, 1, 3)
        opt.g.setColumnStretch(3, 1)
        v.addWidget(opt)

        btns = QHBoxLayout()
        self.bench_btn = QPushButton("Bench CPU")
        self.stress_btn = QPushButton("Stress CPU")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        btns.addWidget(self.bench_btn)
        btns.addWidget(self.stress_btn)
        btns.addWidget(self.progress, 1)
        v.addLayout(btns)
        self.note = QLabel("The benchmark runs a fixed mix of integer hashing and floating-point work in every "
                           "thread (native code). Scores are only comparable between Linux HW-Z runs; results "
                           "are kept in ~/.local/share/linux-hw-z/bench.json.")
        self.note.setWordWrap(True)
        self.note.setProperty("role", "muted")
        v.addWidget(self.note)
        v.addStretch(1)
        self.bench_btn.clicked.connect(self.start_bench)
        self.stress_btn.clicked.connect(self.toggle_stress)
        self.ref.currentIndexChanged.connect(lambda _: self._show_ref())
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)
        self.phase = ""
        self.st_score = self.mt_score = 0.0
        self.m = None
        if not self.runner.available:
            self.bench_btn.setEnabled(False)
            self.stress_btn.setEnabled(False)
            self.note.setText("The native benchmark library (libhwz.so) could not be loaded.")

    def refresh(self, m):
        self.m = m
        self.cpu_name.set(m.cpu.brand)
        self._load_refs()

    def _load_refs(self):
        self.ref.blockSignals(True)
        self.ref.clear()
        self.ref.addItem("None", None)
        for h in reversed(bench.load_history()):
            self.ref.addItem(f"{h.get('cpu', '?')}  ·  {h.get('date', '')}  ·  ST {h.get('st', 0):.0f} / "
                             f"MT {h.get('mt', 0):.0f} ({h.get('threads', '?')}T)", h)
        self.ref.blockSignals(False)
        if self.ref.count() > 1:
            self.ref.setCurrentIndex(1)
        self._show_ref()

    def _scale(self):
        h = self.ref.currentData() or {}
        st = max(self.st_score, h.get("st", 0)) * 1.15 or 1
        mt = max(self.mt_score, h.get("mt", 0)) * 1.15 or 1
        return st, mt

    def _show_ref(self):
        h = self.ref.currentData() or {}
        st, mt = self._scale()
        self.st_ref.show_score(h.get("st", 0), st)
        self.mt_ref.show_score(h.get("mt", 0), mt)
        self.st_this.show_score(self.st_score, st)
        self.mt_this.show_score(self.mt_score, mt)

    def start_bench(self):
        if self.runner.running:
            self.runner.stop()
            return
        self.st_score = self.mt_score = 0.0
        self._show_ref()
        self.phase = "st"
        self.runner.start(1, float(self.dur.currentData()), "st")
        self._busy(True, "Benchmarking single thread…")

    def toggle_stress(self):
        if self.runner.running:
            self.runner.stop()
            return
        self.phase = "stress"
        self.runner.start(self.threads.value(), 24 * 3600.0, "stress")
        self._busy(True, f"Stressing {self.threads.value()} threads — press Stop to end")

    def _busy(self, on, msg=""):
        self.bench_btn.setText("Stop" if on and self.phase in ("st", "mt") else "Bench CPU")
        self.stress_btn.setText("Stop" if on and self.phase == "stress" else "Stress CPU")
        self.bench_btn.setEnabled(not on or self.phase in ("st", "mt"))
        self.stress_btn.setEnabled(not on or self.phase == "stress")
        self.threads.setEnabled(not on)
        if on:
            self.timer.start()
        else:
            self.timer.stop()
            self.progress.setValue(0)
        self.status.emit(msg)

    def _poll(self):
        r = self.runner
        if self.phase == "stress":
            self.progress.setRange(0, 0)
            if not r.running:
                self.progress.setRange(0, 100)
                self._busy(False, "Stress test stopped")
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(int(r.progress() * 100))
        if r.running:
            return
        stopped = r.stop_flag.value == 1
        if self.phase == "st":
            self.st_score = r.score()
            self._show_ref()
            if stopped:
                self._busy(False, "Benchmark stopped")
                return
            self.phase = "mt"
            r.start(self.threads.value(), float(self.dur.currentData()), "mt")
            self.status.emit(f"Benchmarking {self.threads.value()} threads…")
            return
        elif self.phase == "mt":
            self.mt_score = r.score()
            self.ratio.set(f"{self.mt_score / self.st_score:.2f}" if self.st_score else "")
            self._show_ref()
            if not stopped:
                bench.save_result({"cpu": self.m.cpu.name if self.m else "", "st": round(self.st_score, 1),
                                   "mt": round(self.mt_score, 1), "threads": self.threads.value(),
                                   "date": time.strftime("%Y-%m-%d %H:%M"), "version": __version__})
                keep = self.ref.currentData()
                self._load_refs()
                # keep the previously chosen reference instead of the run we just saved
                for i in range(self.ref.count()):
                    if self.ref.itemData(i) == keep:
                        self.ref.setCurrentIndex(i)
                        break
            self._busy(False, f"Single thread {self.st_score:.1f}, multi thread {self.mt_score:.1f}")
        self.phase = ""

    def shutdown(self):
        self.runner.stop()


class AboutTab(QWidget):
    save_txt = Signal()
    save_html = Signal()
    copy_report = Signal()
    unlock = Signal()
    refresh_all = Signal()
    theme_changed = Signal(str)

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)
        title = QLabel(f"<span style='font-size:20pt;font-weight:700'>{APP_NAME}</span>"
                       f"&nbsp;&nbsp;<span style='font-size:11pt'>Version {__version__}</span>")
        v.addWidget(title)
        d = QLabel("Processor, mainboard, memory and graphics card information for Linux — a CPU-Z and GPU-Z "
                   "style tool in one window. It reads /proc, /sys, DMI/SMBIOS, SPD, hwmon, the DRM drivers, "
                   "NVML, Vulkan, OpenGL, OpenCL and VA-API. Nothing is sent anywhere.")
        d.setWordWrap(True)
        v.addWidget(d)
        tools = Grid("Tools", cols=3)
        b1, b2, b3 = QPushButton("Save Report (.TXT)"), QPushButton("Save Report (.HTML)"), QPushButton("Copy Report")
        tools.place(b1, 0, 0)
        tools.place(b2, 0, 1)
        tools.place(b3, 0, 2)
        self.unlock_btn = QPushButton("Unlock administrator details…")
        b5 = QPushButton("Refresh all")
        tools.place(self.unlock_btn, 1, 0, 1, 2)
        tools.place(b5, 1, 2)
        tools.place(key("Theme", Qt.AlignmentFlag.AlignLeft), 2, 0)
        self.theme = QComboBox()
        self.theme.addItem("Follow system", "system")
        self.theme.addItem("Light", "light")
        self.theme.addItem("Dark", "dark")
        tools.place(self.theme, 2, 1, 1, 2)
        v.addWidget(tools)
        self.admin_state = QLabel("")
        self.admin_state.setProperty("role", "muted")
        self.admin_state.setWordWrap(True)
        v.addWidget(self.admin_state)
        lic = QLabel("MIT License · © 2026 Demosthenes Koptsis<br>"
                     "Uses Qt 6 / PySide6 (LGPL v3) and the PCI ID database (pci.ids, BSD-3 / GPL-2). "
                     "CPU-Z and GPU-Z are trademarks of their owners; this is an independent program and "
                     "contains none of their code or artwork.")
        lic.setWordWrap(True)
        lic.setProperty("role", "muted")
        v.addWidget(lic)
        v.addStretch(1)
        b1.clicked.connect(self.save_txt)
        b2.clicked.connect(self.save_html)
        b3.clicked.connect(self.copy_report)
        self.unlock_btn.clicked.connect(self.unlock)
        b5.clicked.connect(self.refresh_all)
        self.theme.currentIndexChanged.connect(lambda _: self.theme_changed.emit(self.theme.currentData()))

    def set_theme(self, mode):
        for i in range(self.theme.count()):
            if self.theme.itemData(i) == mode:
                self.theme.blockSignals(True)
                self.theme.setCurrentIndex(i)
                self.theme.blockSignals(False)

    def set_admin(self, active: bool, error: str = ""):
        if active:
            self.unlock_btn.setText("Administrator details unlocked")
            self.unlock_btn.setEnabled(False)
            self.admin_state.setText("SMBIOS, SPD, RAPL power and core voltage are being read by the helper "
                                     "(running as root until you close Linux HW-Z).")
        else:
            self.unlock_btn.setText("Unlock administrator details…")
            self.unlock_btn.setEnabled(True)
            self.admin_state.setText(error or "Without administrator rights a few fields stay empty: memory slots "
                                              "and type, CPU package, core voltage and CPU power.")
