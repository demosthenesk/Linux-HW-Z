"""Small, failure-tolerant helpers for reading /sys and /proc.

Every path goes through :func:`P`, so the whole program can be pointed at a
fake root (``HWZ_ROOT=/path/to/tree``) for testing on machines that lack the
hardware.
"""

from __future__ import annotations

import glob as _glob
import os

ROOT = os.environ.get("HWZ_ROOT", "").rstrip("/")


def P(path: str) -> str:
    if ROOT and path.startswith("/"):
        return ROOT + path
    return path


def read(path: str, default: str | None = None) -> str | None:
    try:
        with open(P(path), "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except (OSError, ValueError):
        return default


def read_bytes(path: str, limit: int = 1 << 20) -> bytes | None:
    try:
        with open(P(path), "rb") as fh:
            return fh.read(limit)
    except OSError:
        return None


def read_int(path: str, default: int | None = None, base: int = 10) -> int | None:
    s = read(path)
    if s is None:
        return default
    try:
        return int(s.split()[0], base)
    except (ValueError, IndexError):
        try:
            return int(s, 0)
        except ValueError:
            return default


def exists(path: str) -> bool:
    return os.path.exists(P(path))


def readable(path: str) -> bool:
    return os.access(P(path), os.R_OK)


def listdir(path: str) -> list[str]:
    try:
        return sorted(os.listdir(P(path)))
    except OSError:
        return []


def glob(pattern: str) -> list[str]:
    """Glob relative to the root; results are returned as *logical* paths."""
    hits = sorted(_glob.glob(P(pattern)))
    if ROOT:
        return [h[len(ROOT):] for h in hits]
    return hits


def realpath(path: str) -> str:
    rp = os.path.realpath(P(path))
    if ROOT and rp.startswith(ROOT):
        return rp[len(ROOT):]
    return rp


def link_name(path: str) -> str | None:
    """Basename of a symlink target (e.g. a device's ``driver`` link)."""
    try:
        return os.path.basename(os.readlink(P(path)))
    except OSError:
        return None


def parse_cpulist(s: str | None) -> list[int]:
    out: list[int] = []
    if not s:
        return out
    for part in s.strip().split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def fmt_size(n: float | int | None, unit: str = "B") -> str:
    if n is None:
        return ""
    n = float(n)
    for u in ("", "K", "M", "G", "T"):
        if abs(n) < 1024 or u == "T":
            if u == "":
                return f"{int(n)} {unit}"
            return f"{n:.0f} {u}{unit}" if n == int(n) else f"{n:.1f} {u}{unit}"
        n /= 1024
    return f"{n:.1f} P{unit}"
