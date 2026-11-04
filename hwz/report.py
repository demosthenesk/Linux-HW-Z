"""Text / HTML reports (Tools → Save report), built from the same model as the UI."""

from __future__ import annotations

import html

from . import APP_NAME, __version__
from .probes import cpu as cpumod
from .sysfs import fmt_size


def mhz(v) -> str:
    return f"{v:.1f} MHz" if v else ""


def cpu_rows(m) -> list[tuple[str, str]]:
    c = m.cpu
    rows = [("Name", c.name), ("Specification", c.brand), ("Vendor", c.vendor), ("Code name", c.codename),
            ("Technology", c.technology), ("Package", c.package),
            ("Family / Model / Stepping", f"{c.family:X} / {c.model:X} / {c.stepping:X}"),
            ("Ext. Family / Ext. Model", f"{c.ext_family + c.base_family:X} / {c.model:X}"),
            ("Microcode", c.microcode), ("Sockets / Cores / Threads", f"{c.sockets} / {c.cores} / {c.threads}"),
            ("Max TDP (PL1)", f"{c.tdp_w:.1f} W" if c.tdp_w else ""), ("Instructions", ", ".join(c.instructions)),
            ("Scaling driver / governor", f"{c.scaling_driver} / {c.governor}".strip(" /")),
            ("Address sizes", c.address_sizes)]
    for g in c.groups:
        rows.append((f"{g.name}: count", f"{g.cores} cores, {len(g.cpus)} threads (CPUs {cpumod_list(g.cpus)})"))
        rows.append((f"{g.name}: base / max clock", f"{mhz(g.base_mhz)} / {mhz(g.max_mhz)}".strip(" /")))
        for label, (size, ways) in cpumod.merge_caches(g.caches).items():
            rows.append((f"{g.name}: {label}", f"{size}, {ways}".strip(", ")))
    return [(k, v) for k, v in rows if v]


def cpumod_list(cpus: list[int]) -> str:
    if not cpus:
        return ""
    out, start, prev = [], cpus[0], cpus[0]
    for c in cpus[1:] + [None]:
        if c is not None and c == prev + 1:
            prev = c
            continue
        out.append(f"{start}-{prev}" if start != prev else str(start))
        if c is not None:
            start = prev = c
    return ",".join(out)


def board_rows(m) -> list[tuple[str, str]]:
    b = m.board
    rows = [("System", f"{b.get('system_vendor', '')} {b.get('system', '')}".strip()),
            ("Chassis", b.get("chassis", "")), ("Motherboard", f"{b.get('manufacturer', '')} {b.get('model', '')}".strip()),
            ("Board revision", b.get("board_version", "")), ("Bus specs", b.get("bus_specs", "")),
            ("Chipset", f"{b.get('chipset_vendor', '')} {b.get('chipset', '')} rev. {b.get('chipset_rev', '')}"
             if b.get("chipset") else ""),
            ("Southbridge", f"{b.get('south_vendor', '')} {b.get('southbridge', '')} rev. {b.get('south_rev', '')}"
             if b.get("southbridge") else ""),
            ("BIOS brand", b.get("bios_brand", "")), ("BIOS version", b.get("bios_version", "")),
            ("BIOS date", b.get("bios_date", "")), ("Firmware", b.get("uefi", "")),
            ("Secure Boot", b.get("secure_boot", ""))]
    return [(k, v) for k, v in rows if v]


def memory_rows(m) -> list[tuple[str, str]]:
    mm = m.memory()
    rows = [("Type", mm["type"]), ("Installed", fmt_size((mm["installed_mb"] or 0) << 20) if mm["installed_mb"] else ""),
            ("Usable (kernel)", fmt_size(mm["total"])), ("Channels", mm["channels"]),
            ("Speed", f"{mm['configured_speed']} MT/s" if mm["configured_speed"] else ""),
            ("Slots", f"{mm['slots_used']} of {mm['slots_total']} used" if mm["slots_total"] else "")]
    t = mm.get("timings")
    if t:
        rows.append(("Timings (JEDEC, nearest)", f"{t['cl']}-{t['trcd']}-{t['trp']}-{t['tras']} tRC {t['trc']}"))
    for i, mod in enumerate(mm["modules"]):
        if mod["size_mb"]:
            rows.append((f"Slot {mod['locator'] or i}", f"{fmt_size(mod['size_mb'] << 20)} {mod['type']} {mod['form']} "
                         f"{mod['speed']} MT/s {mod['manufacturer']} {mod['part']}".strip()))
    for mod in m.spd_modules:
        rows.append((f"SPD {mod.get('address', '')}",
                     f"{mod.get('speed_name', '')} {mod.get('module', '')} {fmt_size(mod.get('size_mb', 0) << 20)} "
                     f"{mod.get('manufacturer', '')} {mod.get('part', '')}".strip()))
    return [(k, v) for k, v in rows if v]


def gpu_rows(g) -> list[tuple[str, str]]:
    a = g.apis
    vk, gl, cl, va = a.get("vulkan", {}), a.get("opengl", {}), a.get("opencl", {}), a.get("vaapi", {})
    rows = [("Name", g.title), ("GPU", g.gpu), ("Technology", g.technology), ("Revision", g.revision),
            ("Subvendor", g.subvendor), ("Device ID", g.device_id), ("PCI slot", g.dev.short_slot),
            ("Bus interface", g.bus), ("Kernel driver", f"{g.driver} {g.driver_version}"),
            ("Userspace driver", vk.get("driver_info") or (gl.get("version") if gl else "")),
            ("BIOS", g.vbios), ("Memory size", fmt_size(g.memory_size) if g.memory_size else g.memory_type),
            ("Memory vendor", g.memory_vendor), ("Bus width", f"{g.bus_width} bit" if g.bus_width else ""),
            ("Shaders", g.shaders), ("Boost / max clock", mhz(g.clk_boost)), ("Base clock", mhz(g.clk_base)),
            ("Min clock", mhz(g.clk_min)), ("Max memory clock", mhz(g.mem_clk_max)),
            ("Power limit", f"{g.power_limit_w:.0f} W" if g.power_limit_w else ""),
            ("Vulkan", f"{vk.get('api', '')} ({vk.get('driver_name', '')})" if vk else ""),
            ("Ray tracing", "Yes" if vk.get("ray_tracing") else ("No" if vk else "")),
            ("OpenGL", gl.get("version", "") if gl else ""), ("OpenGL renderer", gl.get("renderer", "") if gl else ""),
            ("OpenCL", f"{cl.get('version', '')} ({cl.get('platform', '')})" if cl else ""),
            ("CUDA", a.get("cuda", {}).get("version", "") if a.get("cuda") else ""),
            ("VA-API", f"{va.get('version', '')} {va.get('driver', '')}" if va and not va.get("error") else "")]
    if va and va.get("profiles"):
        dec = [p["profile"] for p in va["profiles"] if "Decode" in p["entrypoints"]]
        enc = [p["profile"] for p in va["profiles"] if any(e.startswith("Encode") for e in p["entrypoints"])]
        rows.append(("Video decode", ", ".join(dec)))
        rows.append(("Video encode", ", ".join(enc)))
    return [(k, v) for k, v in rows if v and str(v).strip()]


def sections(m) -> list[tuple[str, list[tuple[str, str]]]]:
    os_ = m.os
    secs = [("System", [("Operating system", os_.get("distro", "")), ("Kernel", os_.get("kernel", "")),
                        ("Desktop session", f"{os_.get('desktop', '')} {os_.get('session', '')}".strip()),
                        ("Report generated", os_.get("time", "")), ("Generator", f"{APP_NAME} {__version__}")]),
            ("Processor", cpu_rows(m)), ("Mainboard", board_rows(m)), ("Memory", memory_rows(m))]
    secs[0] = ("System", [(k, v) for k, v in secs[0][1] if v])
    for g in m.gpus:
        secs.append((f"Graphics #{g.index}", gpu_rows(g)))
    return secs


def to_text(m) -> str:
    out = [f"{APP_NAME} {__version__} report", "=" * 60, ""]
    for title, rows in sections(m):
        out.append(title)
        out.append("-" * len(title))
        w = max((len(k) for k, _ in rows), default=10)
        for k, v in rows:
            out.append(f"  {k.ljust(w)}  {v}")
        out.append("")
    return "\n".join(out)


def to_html(m) -> str:
    parts = [f"<!doctype html><html><head><meta charset='utf-8'><title>{APP_NAME} report</title>",
             "<style>body{font:14px system-ui,sans-serif;margin:24px;color:#1d2430;background:#f6f7f9}"
             "h1{font-size:20px}h2{font-size:15px;margin:22px 0 6px;color:#2c5d9c}"
             "table{border-collapse:collapse;background:#fff;min-width:640px;box-shadow:0 1px 2px #0002}"
             "td{padding:5px 10px;border-bottom:1px solid #e6e8ec;vertical-align:top}"
             "td:first-child{color:#5a6270;white-space:nowrap;width:220px}"
             "@media (prefers-color-scheme:dark){body{background:#16181c;color:#e4e6ea}table{background:#1f2227}"
             "td{border-color:#2d3138}td:first-child{color:#9aa2ae}h2{color:#7fb0ef}}</style></head><body>",
             f"<h1>{APP_NAME} {__version__} report</h1>"]
    for title, rows in sections(m):
        parts.append(f"<h2>{html.escape(title)}</h2><table>")
        for k, v in rows:
            parts.append(f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>")
        parts.append("</table>")
    parts.append("</body></html>")
    return "".join(parts)
