"""CPU-Z side: CPU, Caches, Mainboard, Memory and SPD tabs."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..probes import cpu as cpumod
from ..sysfs import fmt_size
from .widgets import Badge, Banner, Field, Grid, key


def _mhz(v):
    return f"{v:.2f} MHz" if v else ""


class CpuTab(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        p = self.proc = Grid("Processor")
        p.row(("Name", 7))
        p.row(("Code Name", 3), ("Max TDP", 2))
        p.row(("Package", 7))
        p.row(("Technology", 3), ("Core Voltage", 2))
        p.row(("Specification", 9))
        p.row(("Family", 2), ("Model", 2), ("Stepping", 2))
        p.row(("Ext. Family", 2), ("Ext. Model", 2), ("Revision", 2))
        p.multi("Instructions", 2)
        self.badge = Badge()
        p.place(self.badge, 0, 8, 4, 2, Qt.AlignmentFlag.AlignCenter)
        for c in range(1, 10):
            p.g.setColumnStretch(c, 1)
        v.addWidget(p)

        low = QHBoxLayout()
        low.setSpacing(6)
        ck = self.clocks = Grid("Clocks (Core #0)", cols=4)
        self.core_combo = QComboBox()
        ck.place(key("Core"), 0, 0)
        ck.place(self.core_combo, 0, 1, 1, 3)
        ck.r = 1
        ck.row(("Core Speed", 3))
        ck.row(("Multiplier", 3))
        ck.row(("Bus Speed", 3))
        ck.row(("Base / Max", 3))
        ck.g.setColumnStretch(1, 1)
        low.addWidget(ck, 1)
        ca = self.cache = Grid("Cache", cols=4)
        for lab in ("L1 Data", "L1 Inst.", "Level 2", "Level 3"):
            ca.row((lab, 2), (f"~{lab}", 1))
        ca.g.setColumnStretch(1, 3)
        ca.g.setColumnStretch(3, 1)
        low.addWidget(ca, 1)
        v.addLayout(low)

        sel = QHBoxLayout()
        sel.addWidget(key("Selection"))
        self.sel_combo = QComboBox()
        sel.addWidget(self.sel_combo, 2)
        sel.addSpacing(12)
        sel.addWidget(key("Cores"))
        self.cores = Field(centered=True, width=56)
        sel.addWidget(self.cores)
        sel.addWidget(key("Threads"))
        self.threads = Field(centered=True, width=56)
        sel.addWidget(self.threads)
        v.addLayout(sel)
        v.addStretch(1)
        self.sel_combo.currentIndexChanged.connect(self._sel_changed)
        self.core_combo.currentIndexChanged.connect(lambda _: self._update_clock())
        self.m = None
        self._last_clocks: dict[int, float] = {}

    def refresh(self, m):
        self.m = m
        c = m.cpu
        P = self.proc
        P.set("Name", c.name)
        P.set("Code Name", c.codename)
        P.set("Max TDP", f"{c.tdp_w:.1f} W" if c.tdp_w else "")
        P.set("Package", c.package or ("admin only — Unlock in About" if not m.admin.active else ""))
        P.set("Technology", c.technology)
        P.set("Core Voltage", c.core_voltage or ("" if m.admin.active else "admin only"))
        P.set("Specification", c.brand)
        P.set("Family", f"{c.base_family:X}")
        P.set("Model", f"{c.base_model:X}")
        P.set("Stepping", f"{c.stepping:X}")
        P.set("Ext. Family", f"{c.base_family + c.ext_family:X}")
        P.set("Ext. Model", f"{c.model:X}")
        P.set("Revision", c.microcode)
        P.set("Instructions", ", ".join(c.instructions))
        sub = c.name.replace(c.vendor_short, "").strip()
        self.badge.set(c.vendor_short, sub)
        self.sel_combo.blockSignals(True)
        self.sel_combo.clear()
        if len(c.groups) > 1:
            self.sel_combo.addItem(f"Socket #1  (all {c.cores} cores)", None)
            for i, g in enumerate(c.groups):
                self.sel_combo.addItem(f"Socket #1  {g.name}s ({g.cores})", i)
            self.sel_combo.setCurrentIndex(1)
        else:
            self.sel_combo.addItem("Socket #1", 0)
        self.sel_combo.blockSignals(False)
        self._sel_changed()

    def _group(self):
        if not self.m:
            return None
        idx = self.sel_combo.currentData()
        return self.m.cpu.groups[idx] if idx is not None else None

    def _sel_changed(self):
        if not self.m:
            return
        c = self.m.cpu
        g = self._group()
        cpus = g.cpus if g else sum((x.cpus for x in c.groups), [])
        lines = g.caches if g else c.all_caches
        merged = cpumod.merge_caches(lines)
        for lab in ("L1 Data", "L1 Inst.", "Level 2", "Level 3"):
            size, ways = merged.get(lab, ("", ""))
            self.cache.set(lab, size)
            self.cache.set(f"~{lab}", ways)
        self.cores.set(g.cores if g else c.cores)
        self.threads.set(len(g.cpus) if g else c.threads)
        self.core_combo.blockSignals(True)
        self.core_combo.clear()
        self.core_combo.addItem("Fastest core", -1)
        for cp in cpus:
            self.core_combo.addItem(f"Core #{cp}", cp)
        self.core_combo.blockSignals(False)
        base = g.base_mhz if g else max((x.base_mhz or 0 for x in c.groups), default=0)
        mx = g.max_mhz if g else c.max_turbo_mhz
        self.clocks.set("Base / Max", " / ".join(x for x in (_mhz(base), _mhz(mx)) if x))
        self.clocks.set("Bus Speed", _mhz(c.bus_mhz))
        self._update_clock()

    def tick(self, clocks: dict[int, float], vcore: float | None):
        self._last_clocks = clocks
        self._update_clock()
        if vcore:
            self.proc.set("Core Voltage", f"{vcore:.3f} V")

    def _update_clock(self):
        if not self.m:
            return
        g = self._group()
        cpus = g.cpus if g else sum((x.cpus for x in self.m.cpu.groups), [])
        want = self.core_combo.currentData()
        clk = self._last_clocks
        if want is None or want == -1:
            vals = [(clk[c], c) for c in cpus if c in clk]
            if not vals:
                return
            mhz, core = max(vals)
        else:
            core = want
            mhz = clk.get(want)
            if mhz is None:
                return
        self.clocks.setTitle(f"Clocks (Core #{core})")
        self.clocks.set("Core Speed", _mhz(mhz))
        bus = self.m.cpu.bus_mhz or 100.0
        self.clocks.set("Multiplier", f"x {mhz / bus:.1f}")


class CachesTab(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        sel = QHBoxLayout()
        sel.addWidget(key("Core type"))
        self.combo = QComboBox()
        sel.addWidget(self.combo, 1)
        v.addLayout(sel)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Cache", "Size", "Instances", "Associativity", "Line", "Shared by"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.table, 1)
        self.note = QLabel()
        self.note.setProperty("role", "muted")
        self.note.setWordWrap(True)
        v.addWidget(self.note)
        self.combo.currentIndexChanged.connect(self._show)
        self.m = None

    def refresh(self, m):
        self.m = m
        self.combo.blockSignals(True)
        self.combo.clear()
        if len(m.cpu.groups) > 1:
            self.combo.addItem("All cores", None)
        for i, g in enumerate(m.cpu.groups):
            self.combo.addItem(f"{g.name}s (CPUs {_cpulist(g.cpus)})", i)
        self.combo.blockSignals(False)
        self._show()

    def _show(self):
        if not self.m:
            return
        idx = self.combo.currentData()
        lines = self.m.cpu.groups[idx].caches if idx is not None else self.m.cpu.all_caches
        self.table.setRowCount(len(lines))
        for r, cl in enumerate(lines):
            vals = [cl.label, cl.size_text(), str(cl.count), cl.ways_text() or "fully associative",
                    f"{cl.line} bytes" if cl.line else "", f"{cl.shared_by} thread(s)"]
            for c, val in enumerate(vals):
                it = QTableWidgetItem(val)
                if c:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, c, it)
        total = sum(cl.size_kb * cl.count for cl in lines)
        self.note.setText(f"Total cache: {fmt_size(total * 1024)}.  Read from /sys/devices/system/cpu/*/cache.")


def _cpulist(cpus):
    from ..report import cpumod_list
    return cpumod_list(cpus)


class BoardTab(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        mb = self.mb = Grid("Motherboard")
        mb.row(("Manufacturer", 9))
        mb.row(("Model", 6), ("Rev~mb", 2))
        mb.row(("System", 9))
        mb.row(("Bus Specs", 9))
        mb.row(("Chipset", 2), ("~chip", 4), ("Rev.", 2))
        mb.row(("Southbridge", 2), ("~south", 4), ("Rev.~s", 2))
        mb.row(("Chassis", 3), ("Family", 4))
        for c in range(1, 10):
            mb.g.setColumnStretch(c, 1)
        v.addWidget(mb)
        bi = self.bios = Grid("BIOS / Firmware")
        bi.row(("Brand", 9))
        bi.row(("Version", 4), ("Date", 3))
        bi.row(("Firmware", 4), ("Secure Boot", 3))
        for c in range(1, 10):
            bi.g.setColumnStretch(c, 1)
        v.addWidget(bi)
        gi = self.gi = Grid("Graphic Interface")
        gi.row(("Bus", 9))
        gi.row(("Current Link Width", 3), ("Max. Supported", 3))
        gi.row(("Current Link Speed", 3), ("Max. Supported~2", 3))
        gi.row(("Graphics Memory", 3), ("Clock Range", 3))
        for c in range(1, 10):
            gi.g.setColumnStretch(c, 1)
        v.addWidget(gi)
        v.addStretch(1)

    def refresh(self, m):
        b = m.board
        self.mb.set("Manufacturer", b.get("manufacturer"))
        self.mb.set("Model", b.get("model"))
        self.mb.set("Rev~mb", b.get("board_version"))
        self.mb.set("System", f"{b.get('system_vendor', '')} {b.get('system', '')}".strip())
        self.mb.set("Bus Specs", b.get("bus_specs"))
        self.mb.set("Chipset", b.get("chipset_vendor"))
        self.mb.set("~chip", b.get("chipset"))
        self.mb.set("Rev.", b.get("chipset_rev"))
        self.mb.set("Southbridge", b.get("south_vendor"))
        self.mb.set("~south", b.get("southbridge"))
        self.mb.set("Rev.~s", b.get("south_rev"))
        self.mb.set("Chassis", b.get("chassis"))
        self.mb.set("Family", b.get("family"))
        self.bios.set("Brand", b.get("bios_brand"))
        self.bios.set("Version", b.get("bios_version"))
        self.bios.set("Date", b.get("bios_date"))
        self.bios.set("Firmware", b.get("uefi"))
        self.bios.set("Secure Boot", b.get("secure_boot") or "unknown")
        g = next((x for x in m.gpus if not x.integrated), m.gpus[0] if m.gpus else None)
        link_rows = ("Current Link Width", "Max. Supported", "Current Link Speed", "Max. Supported~2")
        igpu_rows = ("Graphics Memory", "Clock Range")
        if not g:
            self.gi.set("Bus", "No graphics adapter found")
            for n in link_rows + igpu_rows:
                self.gi.show_field(n, False)
            return
        lk = g.dev.link()
        if g.integrated or not lk["max_gen"]:
            # an on-die GPU has no PCIe link: show what it has instead of empty link fields
            self.gi.set("Bus", f"On-die, no PCIe link  ({g.title}, {g.dev.short_slot})")
            for n in link_rows:
                self.gi.show_field(n, False)
            for n in igpu_rows:
                self.gi.show_field(n, True)
            self.gi.set("Graphics Memory", "Shared with system RAM" if g.integrated else (g.memory_type or ""))
            lo, hi = g.clk_min, g.clk_boost
            self.gi.set("Clock Range", f"{lo:.0f} – {hi:.0f} MHz" if lo and hi else (f"up to {hi:.0f} MHz" if hi else ""))
            return
        for n in link_rows:
            self.gi.show_field(n, True)
        for n in igpu_rows:
            self.gi.show_field(n, False)
        if lk["max_gen"]:
            self.gi.set("Bus", f"PCI-Express {lk['max_gen']}  ({g.title}, slot {g.dev.short_slot})")
            self.gi.set("Current Link Width", f"x{lk['cur_width']}")
            self.gi.set("Max. Supported", f"x{lk['max_width']}")
            self.gi.set("Current Link Speed", lk["cur_speed"].replace(" PCIe", ""))
            self.gi.set("Max. Supported~2", lk["max_speed"].replace(" PCIe", ""))


class MemoryTab(QWidget):
    unlock = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        self.banner = Banner("Memory type, slots and speed come from the SMBIOS table, which only the "
                             "administrator can read.", "Unlock…")
        self.banner.clicked.connect(self.unlock)
        v.addWidget(self.banner)
        g = self.gen = Grid("General")
        g.row(("Type", 3), ("Channel #", 3))
        g.row(("Size", 3), ("Slots", 3))
        g.row(("Usable", 3), ("Max. Capacity", 3))
        for c in range(1, 10):
            g.g.setColumnStretch(c, 1)
        v.addWidget(g)
        t = self.tim = Grid("Timings", cols=6)
        for lab in ("DRAM Frequency", "Data Rate", "CAS# Latency (CL)", "RAS# to CAS# Delay (tRCD)",
                    "RAS# Precharge (tRP)", "Cycle Time (tRAS)", "Bank Cycle Time (tRC)"):
            t.row((lab, 2))
        t.g.setColumnStretch(0, 2)
        t.g.setColumnStretch(1, 1)
        t.g.setColumnStretch(2, 1)
        t.g.setColumnStretch(3, 3)
        self.tnote = QLabel("")
        self.tnote.setProperty("role", "muted")
        self.tnote.setWordWrap(True)
        t.place(self.tnote, 0, 3, 7, 3, Qt.AlignmentFlag.AlignTop)
        v.addWidget(t)
        u = self.use = Grid("Usage")
        u.row(("Used", 3), ("Available", 3))
        u.row(("Swap", 3), ("Swap Free", 3))
        for c in range(1, 10):
            u.g.setColumnStretch(c, 1)
        v.addWidget(u)
        v.addStretch(1)

    def refresh(self, m):
        mm = m.memory()
        self.banner.setVisible(m.smbios is None)
        self.gen.set("Type", mm["type"])
        self.gen.set("Channel #", mm["channels"])
        self.gen.set("Size", fmt_size((mm["installed_mb"] or 0) << 20) if mm["installed_mb"] else "")
        self.gen.set("Usable", fmt_size(mm["total"]))
        self.gen.set("Slots", f"{mm['slots_used']} of {mm['slots_total']} used" if mm["slots_total"] else "")
        self.gen.set("Max. Capacity", fmt_size(mm["max_capacity_kb"] * 1024) if mm["max_capacity_kb"] else "")
        sp = mm["configured_speed"]
        self.tim.set("DRAM Frequency", f"{sp / 2:.1f} MHz" if sp else "")
        self.tim.set("Data Rate", f"{sp} MT/s" if sp else "")
        t = mm.get("timings")
        for lab, k in (("CAS# Latency (CL)", "cl"), ("RAS# to CAS# Delay (tRCD)", "trcd"),
                       ("RAS# Precharge (tRP)", "trp"), ("Cycle Time (tRAS)", "tras"), ("Bank Cycle Time (tRC)", "trc")):
            self.tim.set(lab, f"{t[k]} clocks" if t else "")
        if t:
            how = ("the profile nearest to the configured speed" if mm["configured_speed"]
                   else "the fastest JEDEC profile (unlock to see the configured speed)")
            self.tnote.setText(f"JEDEC timings from the module SPD at {t['freq']} MHz, {how}. "
                               "Linux does not expose the live memory-controller timings.")
        else:
            self.tnote.setText("Timings come from the module SPD EEPROM. They appear when the SPD can be read "
                               "(DDR4/DDR5 modules; soldered LPDDR has no SPD).")
        self.tick(m)

    def tick(self, m):
        from ..probes.memory import meminfo
        mi = meminfo()
        tot, av = mi.get("MemTotal"), mi.get("MemAvailable")
        if tot:
            self.use.set("Used", f"{fmt_size(tot - (av or 0))}  ({(tot - (av or 0)) / tot * 100:.0f} %)")
            self.use.set("Available", fmt_size(av))
        self.use.set("Swap", fmt_size(mi.get("SwapTotal")) if mi.get("SwapTotal") else "none")
        self.use.set("Swap Free", fmt_size(mi.get("SwapFree")) if mi.get("SwapTotal") else "")


class SpdTab(QWidget):
    unlock = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)
        self.banner = Banner("No SPD EEPROM is readable yet. Unlocking loads the read-only ee1004/spd5118 "
                             "drivers and reads the memory slots.", "Unlock…")
        self.banner.clicked.connect(self.unlock)
        v.addWidget(self.banner)
        top = QHBoxLayout()
        top.addWidget(key("Memory Slot Selection"))
        self.slot = QComboBox()
        top.addWidget(self.slot, 1)
        v.addLayout(top)
        g = self.g = Grid("Module")
        g.row(("Module Size", 3), ("Type", 3))
        g.row(("Max Bandwidth", 3), ("Module", 3))
        g.row(("Module Manuf.", 3), ("Week/Year", 3))
        g.row(("DRAM Manuf.", 3), ("Ranks", 3))
        g.row(("Part Number", 3), ("Correction", 3))
        g.row(("Serial Number", 3), ("Registered", 3))
        g.row(("SPD Ext.", 3), ("Source", 3))
        for c in range(1, 10):
            g.g.setColumnStretch(c, 1)
        v.addWidget(g)
        self.table = QTableWidget(6, 0)
        self.table.setVerticalHeaderLabels(["Frequency", "CAS# Latency", "RAS# to CAS#", "RAS# Precharge",
                                            "tRAS", "tRC", "Voltage"][:6])
        self.table.setRowCount(7)
        self.table.setVerticalHeaderLabels(["Frequency", "CAS# Latency", "RAS# to CAS#", "RAS# Precharge",
                                            "tRAS", "tRC", "Voltage"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(200)
        box = Grid("Timings Table", cols=1)
        box.add_row_widget(self.table)
        v.addWidget(box, 1)
        self.slot.currentIndexChanged.connect(self._show)
        self.items: list[dict] = []

    def refresh(self, m):
        self.items = []
        for mod in m.spd_modules:
            self.items.append({"kind": "spd", **mod})
        if not self.items and m.smbios:
            for mod in m.smbios.get("memory", []):
                self.items.append({"kind": "dmi", **mod})
        self.banner.setVisible(not m.spd_modules)
        self.slot.blockSignals(True)
        self.slot.clear()
        for i, it in enumerate(self.items):
            if it["kind"] == "spd":
                self.slot.addItem(f"Slot #{i + 1}  ({it.get('address', '')})  {it.get('speed_name', '')}")
            else:
                self.slot.addItem(f"{it.get('locator') or 'Slot'} {it.get('bank', '')}  "
                                  f"{'empty' if not it['size_mb'] else it['type']}  (SMBIOS)")
        if not self.items:
            self.slot.addItem("No module information available")
        self.slot.blockSignals(False)
        self._show()

    def _show(self):
        i = self.slot.currentIndex()
        it = self.items[i] if 0 <= i < len(self.items) else {}
        g = self.g
        if it.get("kind") == "spd":
            g.set("Module Size", fmt_size(it.get("size_mb", 0) << 20))
            g.set("Type", it.get("type"))
            mx = it.get("max_mhz") or 0
            g.set("Max Bandwidth", f"{it.get('speed_name', '')} ({mx} MHz)" if mx else "")
            g.set("Module", it.get("module"))
            g.set("Module Manuf.", it.get("manufacturer"))
            wk, yr = it.get("week"), it.get("year")
            g.set("Week/Year", f"{wk:02d} / {yr % 100:02d}" if wk and yr else "")
            g.set("DRAM Manuf.", it.get("dram_manufacturer"))
            g.set("Ranks", {1: "Single", 2: "Dual", 4: "Quad"}.get(it.get("ranks"), str(it.get("ranks", ""))))
            g.set("Part Number", it.get("part"))
            g.set("Correction", "ECC" if it.get("ecc") else "None")
            g.set("Serial Number", it.get("serial"))
            g.set("Registered", "Yes" if it.get("registered") else "No")
            g.set("SPD Ext.", it.get("ext", ""))
            g.set("Source", "SPD EEPROM")
            rows = it.get("timings") or []
        elif it.get("kind") == "dmi":
            g.set("Module Size", fmt_size(it["size_mb"] << 20) if it["size_mb"] else "empty")
            g.set("Type", it.get("type"))
            sp = it.get("speed") or 0
            g.set("Max Bandwidth", f"{it.get('type', '')}-{sp} ({sp // 2} MHz)" if sp else "")
            g.set("Module", it.get("form"))
            g.set("Module Manuf.", it.get("manufacturer"))
            g.set("Week/Year", "")
            g.set("DRAM Manuf.", "")
            g.set("Ranks", {1: "Single", 2: "Dual", 4: "Quad"}.get(it.get("rank"), ""))
            g.set("Part Number", it.get("part"))
            tw, dw = it.get("total_width") or 0, it.get("data_width") or 0
            g.set("Correction", "ECC" if tw and dw and tw > dw else "None")
            g.set("Serial Number", it.get("serial"))
            g.set("Registered", "")
            g.set("SPD Ext.", "")
            g.set("Source", "SMBIOS (SPD not readable)")
            rows = []
        else:
            for n in g.f:
                g.set(n, "")
            rows = []
        self.table.setColumnCount(len(rows))
        self.table.setHorizontalHeaderLabels([f"JEDEC #{k + 1}" for k in range(len(rows))])
        for c, r in enumerate(rows):
            vals = [f"{r['freq']} MHz", r["cl"], r["trcd"], r["trp"], r["tras"], r["trc"], r["voltage"]]
            for rr, val in enumerate(vals):
                item = QTableWidgetItem(f"{val:.1f}" if isinstance(val, float) else str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(rr, c, item)
