"""PCI devices from /sys/bus/pci plus names from the pci.ids database."""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..sysfs import link_name, listdir, read, read_int

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCI_IDS_PATHS = [
    os.path.join(_HERE, "data", "pci.ids"),          # bundled copy (AppImage)
    "/usr/share/misc/pci.ids", "/usr/share/hwdata/pci.ids", "/usr/share/pci.ids",
]


class PciIds:
    def __init__(self):
        self.vendors: dict[int, str] = {}
        self.devices: dict[tuple[int, int], str] = {}
        self.subsys: dict[tuple[int, int, int, int], str] = {}
        self.classes: dict[tuple[int, int], str] = {}
        self.source = ""
        self.version = ""
        for p in PCI_IDS_PATHS:
            if os.path.exists(p):
                # prefer the newer of bundled/system databases
                self._load(p)
                break

    def _load(self, path: str):
        self.source = path
        ven = dev = None
        cls = None
        try:
            fh = open(path, "r", encoding="utf-8", errors="replace")
        except OSError:
            return
        with fh:
            for line in fh:
                if line.startswith("#"):
                    if "Version:" in line and not self.version:
                        self.version = line.split("Version:", 1)[1].strip()
                    continue
                if not line.strip():
                    continue
                if line.startswith("C "):
                    parts = line[2:].strip().split(None, 1)
                    cls = int(parts[0], 16)
                    ven = None
                    self.classes[(cls, -1)] = parts[1] if len(parts) > 1 else ""
                    continue
                if cls is not None and line.startswith("\t") and not line.startswith("\t\t"):
                    parts = line.strip().split(None, 1)
                    try:
                        self.classes[(cls, int(parts[0], 16))] = parts[1] if len(parts) > 1 else ""
                    except ValueError:
                        pass
                    continue
                if not line.startswith("\t"):
                    cls = None
                    parts = line.strip().split(None, 1)
                    try:
                        ven = int(parts[0], 16)
                    except ValueError:
                        ven = None
                        continue
                    self.vendors[ven] = parts[1] if len(parts) > 1 else ""
                    dev = None
                elif line.startswith("\t\t") and ven is not None and dev is not None:
                    parts = line.strip().split(None, 2)
                    if len(parts) >= 3:
                        try:
                            self.subsys[(ven, dev, int(parts[0], 16), int(parts[1], 16))] = parts[2]
                        except ValueError:
                            pass
                elif ven is not None:
                    parts = line.strip().split(None, 1)
                    try:
                        dev = int(parts[0], 16)
                    except ValueError:
                        continue
                    self.devices[(ven, dev)] = parts[1] if len(parts) > 1 else ""

    def vendor(self, v: int) -> str:
        return self.vendors.get(v, "")

    def device(self, v: int, d: int) -> str:
        return self.devices.get((v, d), "")

    def subsystem(self, v: int, d: int, sv: int, sd: int) -> str:
        return self.subsys.get((v, d, sv, sd), "")


_ids: PciIds | None = None


def ids() -> PciIds:
    global _ids
    if _ids is None:
        _ids = PciIds()
    return _ids


SHORT_VENDOR = {
    0x8086: "Intel", 0x1002: "AMD", 0x1022: "AMD", 0x10DE: "NVIDIA", 0x1028: "Dell", 0x103C: "HP",
    0x17AA: "Lenovo", 0x1043: "ASUS", 0x1462: "MSI", 0x1458: "Gigabyte", 0x1849: "ASRock",
    0x1025: "Acer", 0x144D: "Samsung", 0x1179: "Toshiba", 0x1D05: "Tongfang", 0x1558: "Clevo",
    0x1D72: "Xiaomi", 0x1E83: "Huawei", 0x19DA: "Zotac", 0x1569: "Palit", 0x1682: "XFX",
    0x174B: "Sapphire", 0x148C: "PowerColor", 0x196D: "Club 3D", 0x3842: "EVGA", 0x10B0: "Gainward",
    0x1EAE: "XFX", 0x1DA2: "Sapphire", 0x7377: "Colorful", 0x1AF4: "Red Hat (virtio)", 0x15AD: "VMware",
    0x80EE: "VirtualBox", 0x1234: "QEMU", 0x1B36: "Red Hat (QEMU)", 0x5143: "Qualcomm", 0x1E50: "Moore Threads",
}


def short_vendor(v: int) -> str:
    if v in SHORT_VENDOR:
        return SHORT_VENDOR[v]
    name = ids().vendor(v)
    for cut in (" Corporation", " Corp.", " Inc.", " Co., Ltd.", " Ltd.", " Limited", " Technology", ","):
        name = name.split(cut)[0]
    return name.strip()


@dataclass
class PciDev:
    slot: str            # 0000:00:02.0
    vendor: int
    device: int
    subvendor: int
    subdevice: int
    cls: int             # 24-bit class code
    revision: int
    driver: str | None
    path: str

    @property
    def short_slot(self) -> str:
        return self.slot[5:] if self.slot.startswith("0000:") else self.slot

    def vendor_name(self) -> str:
        return ids().vendor(self.vendor)

    def device_name(self) -> str:
        return ids().device(self.vendor, self.device)

    def subsys_name(self) -> str:
        return ids().subsystem(self.vendor, self.device, self.subvendor, self.subdevice)

    def class_name(self) -> str:
        c = ids().classes
        return c.get((self.cls >> 16, (self.cls >> 8) & 0xFF)) or c.get((self.cls >> 16, -1), "")

    def link(self) -> dict:
        """Current and maximum PCIe link, if the device has one."""
        def gen(speed: str | None) -> str:
            if not speed:
                return ""
            try:
                gt = float(speed.split()[0])
            except ValueError:
                return ""
            return {2.5: "1.1", 5.0: "2.0", 8.0: "3.0", 16.0: "4.0", 32.0: "5.0", 64.0: "6.0"}.get(gt, "")
        cs, ms = read(f"{self.path}/current_link_speed"), read(f"{self.path}/max_link_speed")
        cw, mw = read(f"{self.path}/current_link_width"), read(f"{self.path}/max_link_width")
        return {"cur_gen": gen(cs), "max_gen": gen(ms), "cur_width": cw or "", "max_width": mw or "",
                "cur_speed": cs or "", "max_speed": ms or ""}


def devices() -> list[PciDev]:
    out = []
    base = "/sys/bus/pci/devices"
    for slot in listdir(base):
        p = f"{base}/{slot}"
        v = read_int(f"{p}/vendor", base=16)
        d = read_int(f"{p}/device", base=16)
        if v is None or d is None:
            continue
        out.append(PciDev(slot=slot, vendor=v, device=d,
                          subvendor=read_int(f"{p}/subsystem_vendor", 0, 16) or 0,
                          subdevice=read_int(f"{p}/subsystem_device", 0, 16) or 0,
                          cls=read_int(f"{p}/class", 0, 16) or 0,
                          revision=read_int(f"{p}/revision", 0, 16) or 0,
                          driver=link_name(f"{p}/driver"), path=p))
    return out


def split_name(name: str) -> tuple[str, str]:
    """'AD104 [GeForce RTX 4070]' -> ('AD104', 'GeForce RTX 4070')."""
    if "[" in name and name.rstrip().endswith("]"):
        head, tail = name.split("[", 1)
        return head.strip(), tail.rstrip()[:-1].strip()
    return "", name.strip()
