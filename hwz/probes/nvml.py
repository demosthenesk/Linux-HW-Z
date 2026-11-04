"""Minimal NVML binding (NVIDIA proprietary driver) via ctypes."""

from __future__ import annotations

import ctypes
import os

_lib = None
_ok = False
_handles: dict[str, ctypes.c_void_p] = {}


class _Mem(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


class _Util(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


def _init() -> bool:
    global _lib, _ok
    if _lib is not None:
        return _ok
    names = [os.environ.get("HWZ_NVML_LIB", ""), "libnvidia-ml.so.1", "libnvidia-ml.so"]
    for n in names:
        if not n:
            continue
        try:
            _lib = ctypes.CDLL(n)
            break
        except OSError:
            continue
    if not _lib:
        _lib = False
        return False
    try:
        init = getattr(_lib, "nvmlInit_v2", None) or _lib.nvmlInit
        _ok = init() == 0
    except Exception:
        _ok = False
    return _ok


def _fn(name):
    return getattr(_lib, name, None) if _lib else None


def _handle(slot: str):
    if slot in _handles:
        return _handles[slot]
    h = ctypes.c_void_p()
    f = _fn("nvmlDeviceGetHandleByPciBusId_v2") or _fn("nvmlDeviceGetHandleByPciBusId")
    if not f:
        return None
    # NVML wants "00000000:01:00.0"
    dom, rest = slot.split(":", 1)
    bus_id = f"{int(dom, 16):08X}:{rest}".encode()
    if f(ctypes.c_char_p(bus_id), ctypes.byref(h)) != 0:
        return None
    _handles[slot] = h
    return h


def _uint(name, h, *args):
    f = _fn(name)
    if not f:
        return None
    v = ctypes.c_uint()
    try:
        r = f(h, *args, ctypes.byref(v))
    except Exception:
        return None
    return v.value if r == 0 else None


def _str(name, h=None, size=96):
    f = _fn(name)
    if not f:
        return ""
    buf = ctypes.create_string_buffer(size)
    try:
        r = f(h, buf, ctypes.c_uint(size)) if h is not None else f(buf, ctypes.c_uint(size))
    except Exception:
        return ""
    return buf.value.decode("utf-8", "replace") if r == 0 else ""


def available() -> bool:
    return _init()


def static(slot: str) -> dict | None:
    if not _init():
        return None
    h = _handle(slot)
    if h is None:
        return None
    out = {"name": _str("nvmlDeviceGetName", h), "vbios": _str("nvmlDeviceGetVbiosVersion", h),
           "driver": _str("nvmlSystemGetDriverVersion")}
    m = _Mem()
    f = _fn("nvmlDeviceGetMemoryInfo")
    if f and f(h, ctypes.byref(m)) == 0:
        out["mem_total"] = m.total
    out["bus_width"] = _uint("nvmlDeviceGetMemoryBusWidth", h)
    out["cores"] = _uint("nvmlDeviceGetNumGpuCores", h)
    out["max_gfx"] = _uint("nvmlDeviceGetMaxClockInfo", h, ctypes.c_int(0))
    out["max_mem"] = _uint("nvmlDeviceGetMaxClockInfo", h, ctypes.c_int(2))
    pl = _uint("nvmlDeviceGetEnforcedPowerLimit", h)
    out["power_limit_w"] = pl / 1000 if pl else None
    out["pcie_max_gen"] = _uint("nvmlDeviceGetMaxPcieLinkGeneration", h)
    out["pcie_max_width"] = _uint("nvmlDeviceGetMaxPcieLinkWidth", h)
    out["pcie_cur_gen"] = _uint("nvmlDeviceGetCurrPcieLinkGeneration", h)
    out["pcie_cur_width"] = _uint("nvmlDeviceGetCurrPcieLinkWidth", h)
    return out


def sample(slot: str) -> dict:
    if not _init():
        return {}
    h = _handle(slot)
    if h is None:
        return {}
    out = {}
    out["GPU Clock"] = _uint("nvmlDeviceGetClockInfo", h, ctypes.c_int(0))
    out["Memory Clock"] = _uint("nvmlDeviceGetClockInfo", h, ctypes.c_int(2))
    out["Video Clock"] = _uint("nvmlDeviceGetClockInfo", h, ctypes.c_int(3))
    out["GPU Temperature"] = _uint("nvmlDeviceGetTemperature", h, ctypes.c_int(0))
    out["Fan Speed (%)"] = _uint("nvmlDeviceGetFanSpeed", h)
    pw = _uint("nvmlDeviceGetPowerUsage", h)
    out["Board Power Draw"] = pw / 1000 if pw is not None else None
    u = _Util()
    f = _fn("nvmlDeviceGetUtilizationRates")
    if f and f(h, ctypes.byref(u)) == 0:
        out["GPU Load"] = u.gpu
        out["Memory Controller Load"] = u.memory
    m = _Mem()
    f = _fn("nvmlDeviceGetMemoryInfo")
    if f and f(h, ctypes.byref(m)) == 0:
        out["Memory Used (Dedicated)"] = m.used / (1 << 20)
    enc = _fn("nvmlDeviceGetEncoderUtilization")
    if enc:
        v, per = ctypes.c_uint(), ctypes.c_uint()
        if enc(h, ctypes.byref(v), ctypes.byref(per)) == 0:
            out["Video Encode Load"] = v.value
    dec = _fn("nvmlDeviceGetDecoderUtilization")
    if dec:
        v, per = ctypes.c_uint(), ctypes.c_uint()
        if dec(h, ctypes.byref(v), ctypes.byref(per)) == 0:
            out["Video Decode Load"] = v.value
    ps = ctypes.c_int()
    f = _fn("nvmlDeviceGetPerformanceState")
    if f and f(h, ctypes.byref(ps)) == 0:
        out["Performance State (P)"] = ps.value
    return out
