"""Entry point: ``python -m hwz`` / ``linux-hw-z``."""

from __future__ import annotations

import argparse
import os
import sys

from . import APP_ID, APP_NAME, __version__


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME}: CPU and graphics card information")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    ap.add_argument("--report", metavar="FILE", help="write a report (.txt or .html) and exit; '-' prints text")
    ap.add_argument("--tab", default="", help="open on this tab (CPU, Caches, Mainboard, Memory, SPD, "
                                              "'Graphics Card', Sensors, Advanced, Bench, About)")
    ap.add_argument("--theme", choices=["system", "light", "dark"], help="colour theme for this run")
    args = ap.parse_args(argv)

    if args.report:
        from . import report
        from .model import Model
        m = Model()
        m.run_api_probe(gl=bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")))
        text = report.to_html(m) if args.report.lower().endswith((".html", ".htm")) else report.to_text(m)
        if args.report == "-":
            sys.stdout.write(text + "\n")
        else:
            with open(args.report, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"Report written to {args.report}")
        return 0

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from .model import Model
    from .ui import theme
    from .ui.window import MainWindow

    QApplication.setApplicationName(APP_ID)
    QApplication.setApplicationDisplayName(APP_NAME)
    QApplication.setDesktopFileName(APP_ID)
    app = QApplication(sys.argv[:1])
    settings = QSettings(APP_ID, APP_ID)
    mode = args.theme or settings.value("theme", "system")
    theme.apply(app, mode)
    model = Model()
    win = MainWindow(model, settings, start_tab=args.tab)
    if args.theme:
        win.about_tab.set_theme(args.theme)
    win.show()
    shot = os.environ.get("HWZ_SHOT")  # testing / README screenshots: grab the window and quit
    if shot:
        from PySide6.QtCore import QTimer

        def grab():
            win.grab().save(shot)
            app.quit()
        QTimer.singleShot(int(os.environ.get("HWZ_SHOT_DELAY", "4000")), grab)
    rc = app.exec()
    model.shutdown()
    return rc


if __name__ == "__main__":
    sys.exit(main())
