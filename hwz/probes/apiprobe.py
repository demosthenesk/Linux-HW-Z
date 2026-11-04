"""Graphics/compute API probe: Vulkan, OpenGL, OpenCL, CUDA, VA-API.

Runs in a *separate process* (``python -m hwz.probes.apiprobe``) because
it loads vendor drivers into the address space; a misbehaving driver can
then only take down the probe, never the main window.  Prints JSON.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys

c_u32, c_u64, c_vp, c_cp = ctypes.c_uint32, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_char_p


def _ver(v: int) -> str:
    return f"{v >> 22 & 0x7F}.{v >> 12 & 0x3FF}.{v & 0xFFF}"


# ------------------------------------------------------------------ Vulkan
def vulkan() -> dict:
    try:
        vk = ctypes.CDLL("libvulkan.so.1")
    except OSError:
        return {"error": "Vulkan loader (libvulkan.so.1) not installed"}
    inst_ver = c_u32(0x400000)
    f = getattr(vk, "vkEnumerateInstanceVersion", None)
    if f:
        f(ctypes.byref(inst_ver))

    class AppInfo(ctypes.Structure):
        _fields_ = [("sType", ctypes.c_int), ("pNext", c_vp), ("pApplicationName", c_cp),
                    ("applicationVersion", c_u32), ("pEngineName", c_cp), ("engineVersion", c_u32),
                    ("apiVersion", c_u32)]

    class InstCI(ctypes.Structure):
        _fields_ = [("sType", ctypes.c_int), ("pNext", c_vp), ("flags", c_u32), ("pApplicationInfo", c_vp),
                    ("enabledLayerCount", c_u32), ("ppEnabledLayerNames", c_vp),
                    ("enabledExtensionCount", c_u32), ("ppEnabledExtensionNames", c_vp)]

    api = min(inst_ver.value, (1 << 22) | (3 << 12))
    app = AppInfo(0, None, b"Linux HW-Z", 1, b"hwz", 1, api)
    ci = InstCI(1, None, 0, ctypes.cast(ctypes.pointer(app), c_vp), 0, None, 0, None)
    inst = c_vp()
    vk.vkCreateInstance.argtypes = [c_vp, c_vp, c_vp]
    r = vk.vkCreateInstance(ctypes.byref(ci), None, ctypes.byref(inst))
    if r != 0:
        return {"error": f"vkCreateInstance failed ({r})", "instance": _ver(inst_ver.value)}
    gpa = vk.vkGetInstanceProcAddr
    gpa.restype = c_vp
    gpa.argtypes = [c_vp, c_cp]

    def fn(name, *argtypes):
        addr = gpa(inst, name.encode())
        if not addr:
            return None
        return ctypes.CFUNCTYPE(ctypes.c_int, *argtypes)(addr)

    enum = fn("vkEnumeratePhysicalDevices", c_vp, c_vp, c_vp)
    props_f = fn("vkGetPhysicalDeviceProperties", c_vp, c_vp)
    props2_f = fn("vkGetPhysicalDeviceProperties2", c_vp, c_vp) or fn("vkGetPhysicalDeviceProperties2KHR", c_vp, c_vp)
    mem_f = fn("vkGetPhysicalDeviceMemoryProperties", c_vp, c_vp)
    ext_f = fn("vkEnumerateDeviceExtensionProperties", c_vp, c_cp, c_vp, c_vp)
    destroy = fn("vkDestroyInstance", c_vp, c_vp)

    n = c_u32(0)
    enum(inst, ctypes.byref(n), None)
    arr = (c_vp * n.value)()
    enum(inst, ctypes.byref(n), arr)
    devices = []
    for pd in arr[:n.value]:
        buf = ctypes.create_string_buffer(4096)
        props_f(pd, buf)
        raw = buf.raw
        u = lambda o: int.from_bytes(raw[o:o + 4], "little")  # noqa: E731
        d = {"api": _ver(u(0)), "driver_version_raw": u(4), "vendor_id": u(8), "device_id": u(12),
             "type": {0: "Other", 1: "Integrated GPU", 2: "Discrete GPU", 3: "Virtual GPU", 4: "CPU"}.get(u(16), "?"),
             "name": raw[20:276].split(b"\0")[0].decode("utf-8", "replace"),
             "max_image_2d": u(300), "max_compute_wg_invocations": None}
        # extensions
        exts = []
        if ext_f:
            en = c_u32(0)
            ext_f(pd, None, ctypes.byref(en), None)
            eb = ctypes.create_string_buffer(260 * max(1, en.value))
            ext_f(pd, None, ctypes.byref(en), eb)
            for i in range(en.value):
                exts.append(eb.raw[i * 260:i * 260 + 256].split(b"\0")[0].decode())
        d["extensions"] = len(exts)
        d["ray_tracing"] = "VK_KHR_ray_tracing_pipeline" in exts or "VK_KHR_ray_query" in exts
        d["video_decode"] = [e for e in exts if e.startswith("VK_KHR_video_decode_")]
        d["video_encode"] = [e for e in exts if e.startswith("VK_KHR_video_encode_")]
        # driver + PCI bus properties (Vulkan 1.2 / extensions)
        if props2_f:
            drv = ctypes.create_string_buffer(1024)
            pcib = ctypes.create_string_buffer(64)
            ctypes.memmove(drv, (1000196000).to_bytes(4, "little"), 4)
            has_pci = "VK_EXT_pci_bus_info" in exts
            if has_pci:
                ctypes.memmove(pcib, (1000212000).to_bytes(4, "little"), 4)
                ctypes.memmove(ctypes.addressof(drv) + 8, ctypes.addressof(pcib).to_bytes(8, "little"), 8)
            p2 = ctypes.create_string_buffer(4096)
            ctypes.memmove(p2, (1000059001).to_bytes(4, "little"), 4)
            ctypes.memmove(ctypes.addressof(p2) + 8, ctypes.addressof(drv).to_bytes(8, "little"), 8)
            props2_f(pd, p2)
            dr = drv.raw
            d["driver_name"] = dr[20:276].split(b"\0")[0].decode("utf-8", "replace")
            d["driver_info"] = dr[276:532].split(b"\0")[0].decode("utf-8", "replace")
            if has_pci:
                pr = pcib.raw
                dom, bus, dev, fn_ = (int.from_bytes(pr[16 + 4 * i:20 + 4 * i], "little") for i in range(4))
                d["pci"] = f"{dom:04x}:{bus:02x}:{dev:02x}.{fn_}"
        # memory heaps
        mb = ctypes.create_string_buffer(1024)
        mem_f(pd, mb)
        mr = mb.raw
        heaps = []
        cnt = int.from_bytes(mr[260:264], "little")
        for i in range(min(cnt, 16)):
            o = 264 + 16 * i
            heaps.append({"size": int.from_bytes(mr[o:o + 8], "little"),
                          "device_local": bool(int.from_bytes(mr[o + 8:o + 12], "little") & 1)})
        d["heaps"] = heaps
        devices.append(d)
    if destroy:
        destroy(inst, None)
    return {"instance": _ver(inst_ver.value), "devices": devices}


# ------------------------------------------------------------------ OpenCL
def opencl() -> dict:
    try:
        cl = ctypes.CDLL("libOpenCL.so.1")
    except OSError:
        return {"error": "OpenCL ICD loader not installed"}
    n = c_u32()
    if cl.clGetPlatformIDs(0, None, ctypes.byref(n)) != 0 or n.value == 0:
        return {"platforms": []}
    plats = (c_vp * n.value)()
    cl.clGetPlatformIDs(n.value, plats, None)

    def info(f, obj, param, kind="str"):
        size = ctypes.c_size_t()
        if f(c_vp(obj), c_u32(param), ctypes.c_size_t(0), None, ctypes.byref(size)) != 0:
            return None
        buf = ctypes.create_string_buffer(max(size.value, 8))
        if f(c_vp(obj), c_u32(param), size, buf, None) != 0:
            return None
        if kind == "str":
            return buf.value.decode("utf-8", "replace").strip()
        if kind == "u32":
            return int.from_bytes(buf.raw[:4], "little")
        if kind == "u64":
            return int.from_bytes(buf.raw[:8], "little")
        return buf.raw[:size.value]

    out = []
    for p in plats:
        pl = {"name": info(cl.clGetPlatformInfo, p, 0x0902), "vendor": info(cl.clGetPlatformInfo, p, 0x0903),
              "version": info(cl.clGetPlatformInfo, p, 0x0901), "devices": []}
        dn = c_u32()
        if cl.clGetDeviceIDs(c_vp(p), c_u64(0xFFFFFFFF), 0, None, ctypes.byref(dn)) == 0 and dn.value:
            devs = (c_vp * dn.value)()
            cl.clGetDeviceIDs(c_vp(p), c_u64(0xFFFFFFFF), dn.value, devs, None)
            for d in devs:
                dd = {"name": info(cl.clGetDeviceInfo, d, 0x102B), "vendor": info(cl.clGetDeviceInfo, d, 0x102C),
                      "driver": info(cl.clGetDeviceInfo, d, 0x102D), "version": info(cl.clGetDeviceInfo, d, 0x102F),
                      "type": info(cl.clGetDeviceInfo, d, 0x1000, "u64"),
                      "vendor_id": info(cl.clGetDeviceInfo, d, 0x1001, "u32"),
                      "compute_units": info(cl.clGetDeviceInfo, d, 0x1002, "u32"),
                      "max_clock": info(cl.clGetDeviceInfo, d, 0x100C, "u32"),
                      "global_mem": info(cl.clGetDeviceInfo, d, 0x101F, "u64")}
                raw = info(cl.clGetDeviceInfo, d, 0x410F, "raw")
                if raw and len(raw) >= 16:
                    dom, bus, dev, fn_ = (int.from_bytes(raw[4 * i:4 * i + 4], "little") for i in range(4))
                    dd["pci"] = f"{dom:04x}:{bus:02x}:{dev:02x}.{fn_}"
                pl["devices"].append(dd)
        out.append(pl)
    return {"platforms": out}


# ------------------------------------------------------------------ CUDA
def cuda() -> dict:
    try:
        cu = ctypes.CDLL("libcuda.so.1")
    except OSError:
        return {"available": False}
    if cu.cuInit(0) != 0:
        return {"available": False, "error": "cuInit failed"}
    v = ctypes.c_int()
    cu.cuDriverGetVersion(ctypes.byref(v))
    return {"available": True, "version": f"{v.value // 1000}.{v.value % 1000 // 10}"}


# ------------------------------------------------------------------ VA-API
VA_PROFILES = {
    0: "MPEG2 Simple", 1: "MPEG2 Main", 2: "MPEG4 Simple", 3: "MPEG4 Advanced Simple", 4: "MPEG4 Main",
    5: "H.264 Baseline", 6: "H.264 Main", 7: "H.264 High", 8: "VC-1 Simple", 9: "VC-1 Main",
    10: "VC-1 Advanced", 11: "H.263 Baseline", 12: "JPEG Baseline", 13: "H.264 Constrained Baseline",
    14: "VP8", 15: "H.264 Multiview High", 16: "H.264 Stereo High", 17: "HEVC Main", 18: "HEVC Main 10",
    19: "VP9 Profile 0", 20: "VP9 Profile 1", 21: "VP9 Profile 2", 22: "VP9 Profile 3", 23: "HEVC Main 12",
    24: "HEVC Main 4:2:2 10", 25: "HEVC Main 4:2:2 12", 26: "HEVC Main 4:4:4", 27: "HEVC Main 4:4:4 10",
    28: "HEVC Main 4:4:4 12", 29: "HEVC SCC Main", 30: "HEVC SCC Main 10", 31: "HEVC SCC Main 4:4:4",
    32: "AV1 Profile 0", 33: "AV1 Profile 1", 34: "HEVC SCC Main 4:4:4 10", 35: "Protected",
    36: "H.264 High 10", 37: "VVC Main 10", 38: "VVC Multilayer Main 10", -1: "None (video processing)",
}
VA_ENTRY = {1: "Decode", 2: "IZZ", 3: "IDCT", 4: "MoComp", 5: "Deblocking", 6: "Encode",
            7: "Encode (picture)", 8: "Encode (low power)", 10: "Video processing", 11: "FEI", 12: "Stats",
            13: "Protected TEE", 14: "Protected content"}


def vaapi(render: str) -> dict:
    try:
        va = ctypes.CDLL("libva.so.2")
        vadrm = ctypes.CDLL("libva-drm.so.2")
    except OSError:
        return {"error": "libva not installed"}
    try:
        fd = os.open(render, os.O_RDWR)
    except OSError as e:
        return {"error": str(e)}
    try:
        vadrm.vaGetDisplayDRM.restype = c_vp
        dpy = c_vp(vadrm.vaGetDisplayDRM(fd))
        if not dpy.value:
            return {"error": "vaGetDisplayDRM failed"}
        va.vaInitialize.argtypes = [c_vp, c_vp, c_vp]
        maj, mnr = ctypes.c_int(), ctypes.c_int()
        st = va.vaInitialize(dpy, ctypes.byref(maj), ctypes.byref(mnr))
        if st != 0:
            return {"error": f"vaInitialize failed ({st}); no VA-API driver for this GPU?"}
        va.vaQueryVendorString.restype = c_cp
        va.vaQueryVendorString.argtypes = [c_vp]
        vendor = (va.vaQueryVendorString(dpy) or b"").decode("utf-8", "replace")
        va.vaMaxNumProfiles.argtypes = [c_vp]
        va.vaMaxNumEntrypoints.argtypes = [c_vp]
        np_ = va.vaMaxNumProfiles(dpy)
        ne = va.vaMaxNumEntrypoints(dpy)
        profs = (ctypes.c_int * max(np_, 1))()
        cnt = ctypes.c_int()
        va.vaQueryConfigProfiles.argtypes = [c_vp, c_vp, c_vp]
        va.vaQueryConfigProfiles(dpy, profs, ctypes.byref(cnt))
        va.vaQueryConfigEntrypoints.argtypes = [c_vp, ctypes.c_int, c_vp, c_vp]
        rows = []
        for i in range(cnt.value):
            p = profs[i]
            eps = (ctypes.c_int * max(ne, 1))()
            ec = ctypes.c_int()
            if va.vaQueryConfigEntrypoints(dpy, p, eps, ctypes.byref(ec)) != 0:
                continue
            rows.append({"profile": VA_PROFILES.get(p, f"Profile {p}"),
                         "entrypoints": [VA_ENTRY.get(eps[j], str(eps[j])) for j in range(ec.value)]})
        va.vaTerminate.argtypes = [c_vp]
        va.vaTerminate(dpy)
        return {"version": f"{maj.value}.{mnr.value}", "driver": vendor, "profiles": rows}
    finally:
        os.close(fd)


# ------------------------------------------------------------------ OpenGL (via Qt)
def opengl() -> dict:
    try:
        from PySide6.QtGui import QGuiApplication, QOffscreenSurface, QOpenGLContext, QSurfaceFormat
    except Exception as e:
        return {"error": f"Qt not available: {e}"}
    app = QGuiApplication.instance() or QGuiApplication([sys.argv[0]])  # noqa: F841
    out = {"platform": QGuiApplication.platformName()}

    def ctx_info(fmt):
        surf = QOffscreenSurface()
        surf.setFormat(fmt)
        surf.create()
        ctx = QOpenGLContext()
        ctx.setFormat(fmt)
        if not ctx.create() or not ctx.makeCurrent(surf):
            return None
        f = ctx.functions()
        res = {"vendor": f.glGetString(0x1F00), "renderer": f.glGetString(0x1F01),
               "version": f.glGetString(0x1F02), "glsl": f.glGetString(0x8B8C)}
        try:
            ext = ctx.extensions()
            res["extensions"] = len(ext)
        except Exception:
            pass
        fm = ctx.format()
        res["profile"] = {0: "none", 1: "core", 2: "compatibility"}.get(int(fm.profile().value)
                                                                         if hasattr(fm.profile(), "value")
                                                                         else int(fm.profile()), "")
        res["major"], res["minor"] = fm.majorVersion(), fm.minorVersion()
        res["gles"] = ctx.isOpenGLES()
        ctx.doneCurrent()
        return res

    base = ctx_info(QSurfaceFormat())
    if base:
        out.update(base)
    core = QSurfaceFormat()
    core.setVersion(4, 6)
    core.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    c = ctx_info(core)
    if c:
        out["core_version"] = f"{c['major']}.{c['minor']}"
    return out


def main(argv: list[str]) -> int:
    os.environ.setdefault("LIBVA_MESSAGING_LEVEL", "0")
    renders = [a for a in argv if a.startswith("/dev/dri/")]
    res = {}
    for name, fn in (("vulkan", vulkan), ("opencl", opencl), ("cuda", cuda)):
        try:
            res[name] = fn()
        except Exception as e:
            res[name] = {"error": repr(e)}
    res["vaapi"] = {}
    for r in renders:
        try:
            res["vaapi"][r] = vaapi(r)
        except Exception as e:
            res["vaapi"][r] = {"error": repr(e)}
    if "--no-gl" not in argv:
        try:
            res["opengl"] = opengl()
        except Exception as e:
            res["opengl"] = {"error": repr(e)}
    sys.stdout.write("\nHWZJSON" + json.dumps(res) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    os._exit(main(sys.argv[1:]))
