"""Loader for libhwz.so (CPUID + benchmark kernel), with safe fallbacks."""

from __future__ import annotations

import ctypes
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_lib = None


def lib():
    global _lib
    if _lib is None:
        try:
            l = ctypes.CDLL(os.path.join(_HERE, "libhwz.so"))
            l.hwz_cpuid.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
            l.hwz_cpuid.restype = None
            l.hwz_bench_chunks.argtypes = [ctypes.c_double, ctypes.c_void_p, ctypes.c_uint64]
            l.hwz_bench_chunks.restype = ctypes.c_uint64
            _lib = l
        except OSError:
            _lib = False
    return _lib or None


def cpuid(leaf: int, sub: int = 0) -> tuple[int, int, int, int] | None:
    l = lib()
    if not l:
        return None
    out = (ctypes.c_uint32 * 4)()
    l.hwz_cpuid(leaf, sub, out)
    return out[0], out[1], out[2], out[3]
