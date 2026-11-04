"""Main window."""

from __future__ import annotations

import os
import threading

from PySide6.QtCore import QObject, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from .. import APP_ID, APP_NAME, __version__, report
from ..model import Model
from . import theme
from .tabs_cpu import BoardTab, CachesTab, CpuTab, MemoryTab, SpdTab
from .tabs_gpu import AdvancedTab, GraphicsTab, SensorsTab
from .tabs_misc import AboutTab, BenchTab

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


class _Signals(QObject):
    apis_done = Signal()


class MainWindow(QMainWindow):
    def __init__(self, model: Model, settings: QSettings, start_tab: str = ""):
        super().__init__()
        self.m = model
        self.settings = settings
        self.sig = _Signals()
        self.setWindowTitle(APP_NAME)
        icon = os.path.join(DATA, "linux-hw-z.svg")
        if os.path.exists(icon):
            self.setWindowIcon(QIcon(icon))
        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(6, 6, 6, 4)
        v.setSpacing(4)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.cpu_tab, self.caches_tab, self.board_tab = CpuTab(), CachesTab(), BoardTab()
        self.mem_tab, self.spd_tab = MemoryTab(), SpdTab()
        self.gfx_tab, self.sens_tab, self.adv_tab = GraphicsTab(), SensorsTab(), AdvancedTab()
        self.bench_tab, self.about_tab = BenchTab(), AboutTab()
        for w, name in ((self.cpu_tab, "CPU"), (self.caches_tab, "Caches"), (self.board_tab, "Mainboard"),
                        (self.mem_tab, "Memory"), (self.spd_tab, "SPD"), (self.gfx_tab, "Graphics Card"),
                        (self.sens_tab, "Sensors"), (self.adv_tab, "Advanced"), (self.bench_tab, "Bench"),
                        (self.about_tab, "About")):
            self.tabs.addTab(w, name)
        v.addWidget(self.tabs, 1)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        brand = QLabel(f"{APP_NAME}  <span style='font-weight:400'>Ver. {__version__}</span>")
        brand.setProperty("role", "brand")
        bar.addWidget(brand)
        self.tools = QToolButton()
        self.tools.setText("Tools")
        self.tools.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.tools.setMenu(self._tools_menu())
        bar.addWidget(self.tools)
        self.status = QLabel("")
        self.status.setProperty("role", "muted")
        bar.addWidget(self.status, 1)
        bar.addWidget(QLabel("Graphics:"))
        self.gpu_combo = QComboBox()
        self.gpu_combo.setMinimumContentsLength(18)
        self.gpu_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        bar.addWidget(self.gpu_combo)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        bar.addWidget(close)
        v.addLayout(bar)
        self.setCentralWidget(central)

        # signals
        for t in (self.mem_tab, self.spd_tab, self.sens_tab, self.about_tab):
            t.unlock.connect(self.unlock_admin)
        self.about_tab.save_txt.connect(lambda: self.save_report("txt"))
        self.about_tab.save_html.connect(lambda: self.save_report("html"))
        self.about_tab.copy_report.connect(self.copy_report)
        self.about_tab.refresh_all.connect(self.refresh_all)
        self.about_tab.theme_changed.connect(self.set_theme)
        self.bench_tab.status.connect(self.status.setText)
        self.sens_tab.interval_changed.connect(lambda ms: self.timer.setInterval(ms))
        self.gpu_combo.currentIndexChanged.connect(lambda _: self._gpu_changed())
        self.sig.apis_done.connect(self._apis_done)
        self.tabs.currentChanged.connect(lambda i: self.settings.setValue("tab", i))

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.admin_timer = QTimer(self)
        self.admin_timer.setInterval(200)
        self.admin_timer.timeout.connect(self._admin_poll)

        self.about_tab.set_theme(self.settings.value("theme", "system"))
        self.about_tab.set_admin(False)
        self._fill_gpus()
        self.refresh_tabs()
        self._start_api_probe()
        self.tick()
        self.timer.start()
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(740, 640)
        names = [self.tabs.tabText(i).lower() for i in range(self.tabs.count())]
        if start_tab and start_tab.lower() in names:
            self.tabs.setCurrentIndex(names.index(start_tab.lower()))
        else:
            self.tabs.setCurrentIndex(int(self.settings.value("tab", 0) or 0))
        try:
            QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _: self._scheme_changed())
        except Exception:
            pass

    # ------------------------------------------------------------------ menus
    def _tools_menu(self):
        menu = QMenu(self)
        for text, slot, sc in (("Save Report (.TXT)…", lambda: self.save_report("txt"), "Ctrl+S"),
                               ("Save Report (.HTML)…", lambda: self.save_report("html"), "Ctrl+Shift+S"),
                               ("Copy Report to Clipboard", self.copy_report, "Ctrl+Shift+C"),
                               (None, None, None),
                               ("Unlock Administrator Details…", self.unlock_admin, ""),
                               ("Refresh All", self.refresh_all, "F5")):
            if text is None:
                menu.addSeparator()
                continue
            a = QAction(text, self)
            if sc:
                a.setShortcut(QKeySequence(sc))
                self.addAction(a)
            a.triggered.connect(slot)
            menu.addAction(a)
        tm = menu.addMenu("Theme")
        for label, mode in (("Follow system", "system"), ("Light", "light"), ("Dark", "dark")):
            a = QAction(label, self)
            a.triggered.connect(lambda _=False, md=mode: self.set_theme(md))
            tm.addAction(a)
        return menu

    # ------------------------------------------------------------------ data
    def _fill_gpus(self):
        self.gpu_combo.blockSignals(True)
        self.gpu_combo.clear()
        for g in self.m.gpus:
            self.gpu_combo.addItem(g.title, g.index)
        if not self.m.gpus:
            self.gpu_combo.addItem("none")
        self.gpu_combo.blockSignals(False)

    def gi(self) -> int:
        return max(0, self.gpu_combo.currentIndex())

    def refresh_tabs(self):
        m = self.m
        self.cpu_tab.refresh(m)
        self.caches_tab.refresh(m)
        self.board_tab.refresh(m)
        self.mem_tab.refresh(m)
        self.spd_tab.refresh(m)
        self.bench_tab.refresh(m)
        self._gpu_changed()

    def _gpu_changed(self):
        gi = self.gi()
        self.gfx_tab.show_gpu(self.m, gi)
        self.adv_tab.show_gpu(self.m, gi)
        if self.m.gpus:
            self.sens_tab.set_gpu(self.m.gpus[gi].title)

    def _start_api_probe(self):
        self.status.setText("Detecting graphics APIs…")

        def work():
            try:
                self.m.run_api_probe(gl=bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")))
            finally:
                self.sig.apis_done.emit()
        threading.Thread(target=work, daemon=True).start()

    def _apis_done(self):
        self.status.setText("" if not self.m.apis.get("error") else "Graphics API probe failed")
        self._gpu_changed()

    def refresh_all(self):
        cur = self.gi()
        self.m.refresh_static()
        self._fill_gpus()
        if cur < self.gpu_combo.count():
            self.gpu_combo.setCurrentIndex(cur)
        self.refresh_tabs()
        self.m.apis_ready = False
        self._start_api_probe()

    def tick(self):
        m = self.m
        from ..probes import cpu as cpumod
        clocks = cpumod.current_mhz()
        vcore = max(m.admin.vcore.values()) if m.admin.active and m.admin.vcore else None
        self.cpu_tab.tick(clocks, vcore)
        gvals = {}
        if m.gpus:
            gvals = m.gpu_samplers[self.gi()].sample()
            self.gfx_tab.tick(gvals)
        sysv = m.system.sample(m.admin)
        self.sens_tab.update_values(gvals, sysv, m.admin.active)
        if self.tabs.currentWidget() is self.mem_tab:
            self.mem_tab.tick(m)

    # ------------------------------------------------------------------ admin
    def unlock_admin(self):
        if self.m.admin.active:
            return
        cpus = [g.cpus[0] for g in self.m.cpu.groups if g.cpus]
        if not self.m.admin.start(cpus, interval=1.0):
            QMessageBox.warning(self, APP_NAME, self.m.admin.error)
            return
        self.status.setText("Waiting for authentication…")
        self.admin_timer.start()

    def _admin_poll(self):
        a = self.m.admin
        if not a.ready.is_set():
            return
        self.admin_timer.stop()
        if a.active and a.got_info:
            self.m.on_admin_ready()
            self.refresh_tabs()
            self.about_tab.set_admin(True)
            self.status.setText("Administrator details unlocked")
        else:
            self.about_tab.set_admin(False, a.error)
            self.status.setText(a.error or "Unlock failed")

    # ------------------------------------------------------------------ reports
    def save_report(self, kind):
        ext = "txt" if kind == "txt" else "html"
        base = os.path.join(os.path.expanduser("~"), f"{APP_ID}-report.{ext}")
        path, _ = QFileDialog.getSaveFileName(self, "Save report", base,
                                              "Text files (*.txt)" if ext == "txt" else "HTML files (*.html)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(report.to_text(self.m) if ext == "txt" else report.to_html(self.m))
            self.status.setText(f"Report saved to {path}")
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, f"Could not save the report:\n{e}")

    def copy_report(self):
        QApplication.clipboard().setText(report.to_text(self.m))
        self.status.setText("Report copied to the clipboard")

    # ------------------------------------------------------------------ theme
    def set_theme(self, mode):
        self.settings.setValue("theme", mode)
        self.about_tab.set_theme(mode)
        theme.apply(QApplication.instance(), mode)
        self._repaint()

    def _scheme_changed(self):
        if self.settings.value("theme", "system") == "system":
            theme.apply(QApplication.instance(), "system")
            self._repaint()

    def _repaint(self):
        for w in self.findChildren(QWidget):
            QWidget.update(w)

    def closeEvent(self, e):
        self.settings.setValue("geometry", self.saveGeometry())
        self.timer.stop()
        self.bench_tab.shutdown()
        self.sens_tab.close_log()
        self.m.shutdown()
        super().closeEvent(e)
