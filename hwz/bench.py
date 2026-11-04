"""CPU benchmark and stress test (native kernel in libhwz.so, one Python thread per core)."""

from __future__ import annotations

import ctypes
import json
import os
import threading
import time

from . import native

SCORE_DIV = 48.0          # chunks/s -> points (an Intel Xeon 8275CL thread at 2.8 GHz scores ~420)
DEFAULT_SECONDS = 4.0


def _results_file() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "linux-hw-z", "bench.json")


def load_history() -> list[dict]:
    try:
        with open(_results_file(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_result(entry: dict) -> None:
    hist = load_history()
    hist.append(entry)
    hist = hist[-50:]
    p = _results_file()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(hist, fh, indent=1)
    except OSError:
        pass


class Runner:
    """Runs N worker threads; progress/score are read by the UI timer."""

    def __init__(self):
        self.stop_flag = ctypes.c_int(0)
        self.threads: list[threading.Thread] = []
        self.counts: list[int] = []
        self.started = 0.0
        self.seconds = 0.0
        self.mode = ""
        self.done = threading.Event()
        self.done.set()
        self.available = native.lib() is not None

    @property
    def running(self) -> bool:
        return not self.done.is_set()

    def start(self, threads: int, seconds: float, mode: str):
        lib = native.lib()
        if lib is None or self.running:
            return False
        self.stop_flag.value = 0
        self.counts = [0] * threads
        self.mode = mode
        self.seconds = seconds
        self.started = time.monotonic()
        self.done.clear()
        alive = [threads]
        lock = threading.Lock()

        def work(i):
            try:
                self.counts[i] = lib.hwz_bench_chunks(ctypes.c_double(seconds), ctypes.addressof(self.stop_flag),
                                                      ctypes.c_uint64(0x9E3779B97F4A7C15 + i))
            finally:
                with lock:
                    alive[0] -= 1
                    if alive[0] == 0:
                        self.finished = time.monotonic()
                        self.done.set()

        self.threads = [threading.Thread(target=work, args=(i,), daemon=True) for i in range(threads)]
        for t in self.threads:
            t.start()
        return True

    def stop(self):
        self.stop_flag.value = 1

    def score(self) -> float:
        el = getattr(self, "finished", 0.0) - self.started
        if el <= 0:
            return 0.0
        return sum(self.counts) / el / SCORE_DIV

    def progress(self) -> float:
        if not self.seconds:
            return 0.0
        return min(1.0, (time.monotonic() - self.started) / self.seconds)
