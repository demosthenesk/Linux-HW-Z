"""Runs the API probe subprocess and merges its results into the GPU list."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

from .gpu import GpuInfo

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_api_probe(gpus: list[GpuInfo], timeout: float = 25.0, gl: bool = True) -> dict:
    renders = [g.render for g in gpus if g.render and os.path.exists(g.render)]
    env = dict(os.environ)
    # the child needs the same import path (bundled PySide6 inside the AppImage)
    paths = [PKG_ROOT] + [p for p in sys.path if p and os.path.isdir(p)]
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(paths))
    env.setdefault("LIBVA_MESSAGING_LEVEL", "0")
    cmd = [sys.executable, "-s", "-m", "hwz.probes.apiprobe", *renders]
    if not gl:
        cmd.append("--no-gl")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=PKG_ROOT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": f"API probe did not finish: {e}"}
    out = r.stdout
    if "HWZJSON" not in out:
        tail = (r.stderr or "").strip().splitlines()[-3:]
        return {"error": f"API probe crashed (exit {r.returncode}). " + " ".join(tail)}
    try:
        return json.loads(out.split("HWZJSON", 1)[1].strip().splitlines()[0])
    except (ValueError, IndexError) as e:
        return {"error": f"API probe output unreadable: {e}"}


def _clean_vk_name(n: str) -> str:
    n = re.sub(r"\s*\((RADV|NVK|LLVM)[^)]*\)", "", n)
    return n.strip()


def merge(gpus: list[GpuInfo], apis: dict) -> None:
    vk = apis.get("vulkan", {}) or {}
    cl = apis.get("opencl", {}) or {}
    gl = apis.get("opengl", {}) or {}
    va = apis.get("vaapi", {}) or {}
    cu = apis.get("cuda", {}) or {}
    for g in gpus:
        a = {}
        slot = g.dev.slot.lower()
        cands = [d for d in vk.get("devices", []) if d.get("pci") == slot] or \
                [d for d in vk.get("devices", []) if d.get("vendor_id") == g.dev.vendor and
                 d.get("device_id") == g.dev.device]
        if cands:
            d = cands[0]
            a["vulkan"] = d
            heaps = [h["size"] for h in d.get("heaps", []) if h.get("device_local")]
            if heaps and g.memory_size is None and not g.integrated:
                g.memory_size = max(heaps)
            if g.dev.vendor in (0x1002, 0x10DE) and not g.extra.get("nvml"):
                nm = _clean_vk_name(d.get("name", ""))
                nm = re.sub(r"^(AMD|NVIDIA)\s+", "", nm)
                if nm and "/" in g.name:
                    g.name = nm
        cld = None
        for p in cl.get("platforms", []):
            for d in p.get("devices", []):
                if d.get("pci") == slot or (not d.get("pci") and d.get("vendor_id") == g.dev.vendor
                                            and (d.get("type") or 0) & 4):
                    cld = dict(d, platform=p.get("name"), platform_version=p.get("version"))
                    break
            if cld:
                break
        if cld:
            a["opencl"] = cld
            cu_n = cld.get("compute_units")
            if cu_n and not g.shaders:
                unit = {0x8086: "EU", 0x1002: "CU", 0x10DE: "SM"}.get(g.dev.vendor, "CU")
                g.shaders = f"{cu_n} {unit}" + (" (OpenCL)" if g.dev.vendor == 0x8086 else "")
        if gl and not gl.get("error"):
            vend = (gl.get("vendor", "") + " " + gl.get("renderer", "")).lower()
            short = {0x8086: "intel", 0x1002: "amd", 0x10DE: "nvidia"}.get(g.dev.vendor, "")
            if (short and short in vend) or len(gpus) == 1 or (g.index == 0 and "llvmpipe" not in vend):
                a["opengl"] = gl
        if g.render in va:
            a["vaapi"] = va[g.render]
        if g.dev.vendor == 0x10DE and cu.get("available"):
            a["cuda"] = cu
        g.apis = a
