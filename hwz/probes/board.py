"""Mainboard tab: DMI identification, chipset/southbridge from PCI, PCIe bus specs."""

from __future__ import annotations

import re

from ..sysfs import read
from . import dmi, pci


def probe() -> dict:
    d = dmi.basic()
    out = {
        "manufacturer": d.get("board_vendor") or d.get("sys_vendor", ""),
        "model": d.get("board_name", ""),
        "board_version": d.get("board_version", ""),
        "system_vendor": d.get("sys_vendor", ""),
        "system": " ".join(x for x in (d.get("product_name", ""), d.get("product_version", "")) if x),
        "family": d.get("product_family", ""),
        "sku": d.get("product_sku", ""),
        "chassis": dmi.CHASSIS.get(int(d.get("chassis_type", "0") or 0), ""),
        "bios_brand": d.get("bios_vendor", ""),
        "bios_version": d.get("bios_version", ""),
        "bios_date": d.get("bios_date", ""),
        "bios_release": d.get("bios_release", ""),
        "ec": d.get("ec_firmware_release", ""),
        "uefi": "UEFI" if read("/sys/firmware/efi/fw_platform_size") or _isdir("/sys/firmware/efi") else "Legacy BIOS",
        "secure_boot": _secure_boot(),
    }
    devs = pci.devices()
    host = next((x for x in devs if x.slot.endswith("00:00.0")), None)
    isa = next((x for x in devs if (x.cls >> 8) == 0x0601), None)
    smbus = next((x for x in devs if (x.cls >> 8) == 0x0C05), None)
    if host:
        out["chipset_vendor"] = pci.short_vendor(host.vendor)
        out["chipset"] = host.device_name() or f"{host.device:04X}"
        out["chipset_rev"] = f"{host.revision:02X}"
    prom = next((x for x in devs if x.vendor == 0x1022 and "Chipset" in (x.device_name() or "")), None)
    if prom:
        name = prom.device_name()
        out["south_vendor"] = "AMD"
        out["southbridge"] = re.sub(r"\s*(PCIe|USB|SATA).*$", "", name) or name
        out["south_rev"] = f"{prom.revision:02X}"
    elif isa:
        out["south_vendor"] = pci.short_vendor(isa.vendor)
        out["southbridge"] = isa.device_name() or f"{isa.device:04X}"
        out["south_rev"] = f"{isa.revision:02X}"
    elif smbus:
        out["south_vendor"] = pci.short_vendor(smbus.vendor)
        out["southbridge"] = smbus.device_name()
        out["south_rev"] = f"{smbus.revision:02X}"
    gens = []
    for x in devs:
        if (x.cls >> 8) == 0x0604:
            g = x.link().get("max_gen")
            if g:
                gens.append(float(g))
    out["bus_specs"] = ""
    if gens:
        mg = max(gens)
        out["bus_specs"] = f"PCI-Express {mg:g}.0" if mg == int(mg) else f"PCI-Express {mg:g}"
        out["bus_specs"] += f" ({ {1.1: 2.5, 2.0: 5.0, 3.0: 8.0, 4.0: 16.0, 5.0: 32.0, 6.0: 64.0}.get(mg, 0):g} GT/s)"
    return out


def _isdir(p: str) -> bool:
    import os
    from ..sysfs import P
    return os.path.isdir(P(p))


def _secure_boot() -> str:
    from ..sysfs import glob, read_bytes
    hits = glob("/sys/firmware/efi/efivars/SecureBoot-*")
    if not hits:
        return ""
    b = read_bytes(hits[0], 8)
    if not b or len(b) < 5:
        return ""
    return "Enabled" if b[4] == 1 else "Disabled"
