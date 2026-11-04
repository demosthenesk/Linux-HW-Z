"""Drive every tab, the admin helper, the benchmark and the reports headlessly.

QT_QPA_PLATFORM=offscreen HWZ_ADMIN_NO_PKEXEC=1 python3 -m tests.ui_smoke
"""
import os
import sys
import tempfile
import time

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from hwz import report
from hwz.model import Model
from hwz.ui import theme
from hwz.ui.window import MainWindow

errors = []
import traceback as _tb
sys.excepthook = lambda *a: (errors.append(a), _tb.print_exception(*a))

app = QApplication([])
tmp = tempfile.mkdtemp()
settings = QSettings(os.path.join(tmp, "s.ini"), QSettings.Format.IniFormat)
theme.apply(app, "light")
m = Model()
w = MainWindow(m, settings)
w.show()


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


pump(1)
t0 = time.time()
while not m.apis_ready and time.time() - t0 < 30:
    pump(0.2)
print("apis ready:", m.apis_ready, "error:", m.apis.get("error"))
for i in range(w.tabs.count()):
    w.tabs.setCurrentIndex(i)
    pump(0.15)
for i in range(w.adv_tab.combo.count()):
    w.adv_tab.combo.setCurrentIndex(i)
    pump(0.05)
    print(f"  advanced[{w.adv_tab.combo.currentText()}]: {w.adv_tab.tree.topLevelItemCount()} rows")
for gi in range(w.gpu_combo.count()):
    w.gpu_combo.setCurrentIndex(gi)
    pump(1.2)
print("sensor rows:", len(w.sens_tab.rows))
for mode in ("Minimum", "Maximum", "Average", "Current"):
    w.sens_tab.mode.setCurrentText(mode)
w.set_theme("dark")
pump(0.2)
w.set_theme("light")

if os.environ.get("HWZ_ADMIN_NO_PKEXEC"):
    w.unlock_admin()
    t0 = time.time()
    while w.admin_timer.isActive() and time.time() - t0 < 15:
        pump(0.2)
    pump(2.5)
    print("admin active:", m.admin.active, "got info:", m.admin.got_info, "error:", m.admin.error)

b = w.bench_tab
b.dur.setCurrentIndex(0)
b.start_bench()
t0 = time.time()
while (b.runner.running or b.phase) and time.time() - t0 < 30:
    pump(0.2)
print(f"bench: st={b.st_score:.1f} mt={b.mt_score:.1f} ratio={b.ratio.text()}")
b.toggle_stress()
pump(1.5)
b.toggle_stress()
pump(1.0)
print("stress stopped:", not b.runner.running)

txt = report.to_text(m)
html = report.to_html(m)
print("report lines:", len(txt.splitlines()), "html bytes:", len(html))
w.close()
pump(0.5)
print("admin stopped:", not m.admin.active)
if errors:
    import traceback
    for e in errors:
        traceback.print_exception(*e)
    sys.exit(1)
print("SMOKE OK")
