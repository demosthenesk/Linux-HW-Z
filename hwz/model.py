"""Everything the UI and the reports show, gathered in one place."""

from __future__ import annotations

import platform
import time

from . import __version__
from .admin import AdminSession
from .probes import board, collect, cpu, gpu, memory, spd
from .probes.sensors import SystemSampler


class Model:
    def __init__(self):
        self.admin = AdminSession()
        self.apis: dict = {}
        self.apis_ready = False
        self.refresh_static()

    def refresh_static(self):
        self.cpu = cpu.probe()
        self.board = board.probe()
        self.gpus = gpu.probe()
        self.spd_user = spd.read_modules()
        self.system = SystemSampler(self.cpu)
        self.gpu_samplers = [gpu.GpuSampler(g) for g in self.gpus]
        if self.apis:
            collect.merge(self.gpus, self.apis)
        self._apply_admin_static()
        self.os = os_info()

    # ---- admin-derived fields
    @property
    def smbios(self) -> dict | None:
        return self.admin.smbios

    @property
    def spd_modules(self) -> list[dict]:
        return self.admin.spd or self.spd_user

    def memory(self) -> dict:
        return memory.summary(self.smbios, self.spd_modules)

    def _apply_admin_static(self):
        sm = self.smbios
        if not sm:
            return
        procs = sm.get("processors") or []
        if procs:
            p = procs[0]
            self.cpu.package = p.get("upgrade") or p.get("socket") or ""
            if p.get("upgrade", "").startswith("Socket") and p.get("socket"):
                self.cpu.package = p["upgrade"]
            if p.get("ext_clock"):
                self.cpu.bus_mhz = float(p["ext_clock"])

    def on_admin_ready(self):
        self._apply_admin_static()

    def run_api_probe(self, gl: bool = True):
        self.apis = collect.run_api_probe(self.gpus, gl=gl)
        collect.merge(self.gpus, self.apis)
        self.apis_ready = True

    def shutdown(self):
        self.admin.stop()


def os_info() -> dict:
    d = {"kernel": platform.release(), "machine": platform.machine(), "python": platform.python_version(),
         "app": __version__, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        with open("/etc/os-release", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    d["distro"] = line.split("=", 1)[1].strip().strip('"')
    except OSError:
        d["distro"] = "Linux"
    import os
    d["desktop"] = os.environ.get("XDG_CURRENT_DESKTOP", "")
    d["session"] = os.environ.get("XDG_SESSION_TYPE", "")
    return d
