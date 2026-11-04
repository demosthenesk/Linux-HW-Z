#!/usr/bin/python3
"""Linux HW-Z administrator helper.

Started by the main window through ``pkexec /usr/bin/python3 -I this-file``
after the user clicks "Unlock administrator details".  It uses only the
standard library and never writes to the system: it loads the read-only
``msr``/``ee1004``/``spd5118`` drivers if needed, prints one JSON line with
the SMBIOS table and SPD EEPROM dumps, then streams RAPL energy counters and
core voltage once per interval until its stdin is closed.
"""

import base64
import glob
import json
import os
import select
import struct
import subprocess
import sys
import time


def rd(p, n=1 << 20):
    try:
        with open(p, "rb") as f:
            return f.read(n)
    except OSError:
        return None


def modprobe(name):
    for exe in ("/usr/sbin/modprobe", "/sbin/modprobe"):
        if os.path.exists(exe):
            subprocess.run([exe, "-q", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            return


def spd_dumps():
    # i2c-i801 / piix4 instantiate the SPD EEPROMs; the eeprom drivers must be loaded to read them
    for m in ("i2c-dev", "ee1004", "spd5118", "at24"):
        modprobe(m)
    time.sleep(0.3)
    out = {}
    pats = ["/sys/bus/i2c/drivers/ee1004/*-00*/eeprom", "/sys/bus/i2c/drivers/spd5118/*-00*/eeprom",
            "/sys/bus/i2c/drivers/spd5118/*-00*/*/nvmem", "/sys/bus/i2c/drivers/at24/*-005*/eeprom"]
    for pat in pats:
        for p in sorted(glob.glob(pat)):
            dev = [x for x in p.split("/") if "-00" in x]
            key = dev[0] if dev else p
            if key in out:
                continue
            b = rd(p, 1024)
            if b and b[2:3] in (b"\x0b", b"\x0c", b"\x12", b"\x13", b"\x15"):
                out[key] = base64.b64encode(b).decode()
    return out


def cpu_vendor():
    try:
        with open("/proc/cpuinfo") as f:
            txt = f.read(4096)
    except OSError:
        return "", 0, 0
    v = fam = mod = 0
    vend = ""
    for line in txt.splitlines():
        if line.startswith("vendor_id"):
            vend = line.split(":", 1)[1].strip()
        elif line.startswith("cpu family"):
            fam = int(line.split(":", 1)[1])
        elif line.startswith("model\t") or line.startswith("model "):
            mod = int(line.split(":", 1)[1])
        if vend and fam and mod:
            break
    return vend, fam, mod


def read_msr(cpu, reg):
    try:
        fd = os.open(f"/dev/cpu/{cpu}/msr", os.O_RDONLY)
    except OSError:
        return None
    try:
        return struct.unpack("<Q", os.pread(fd, 8, reg))[0]
    except OSError:
        return None
    finally:
        os.close(fd)


def voltage(cpu, vend, fam, mod):
    if vend == "GenuineIntel":
        v = read_msr(cpu, 0x198)
        if v:
            return ((v >> 32) & 0xFFFF) / 8192.0
    elif vend == "AuthenticAMD" and fam >= 0x17:
        v = read_msr(cpu, 0xC0010293)
        if v:
            vid = (v >> 14) & 0xFF
            if (fam == 0x19 and mod >= 0x60) or fam >= 0x1A:
                return 0.245 + vid * 0.005
            return 1.55 - vid * 0.00625
    return None


def rapl_zones():
    zones = {}
    for d in sorted(glob.glob("/sys/class/powercap/intel-rapl*:*")):
        name = (rd(d + "/name") or b"").decode().strip()
        if not os.path.exists(d + "/energy_uj"):
            continue
        rng = rd(d + "/max_energy_range_uj")
        zones[d] = (name, int(rng) if rng and rng.strip().isdigit() else 0)
    return zones


def main():
    interval = 1.0
    cpus = [0]
    for i, a in enumerate(sys.argv):
        if a == "--interval":
            interval = max(0.25, float(sys.argv[i + 1]))
        if a == "--cpus":
            cpus = [int(x) for x in sys.argv[i + 1].split(",") if x.isdigit()]
    parent = os.getppid()
    modprobe("msr")
    vend, fam, mod = cpu_vendor()
    info = {
        "dmi": base64.b64encode(rd("/sys/firmware/dmi/tables/DMI") or b"").decode(),
        "spd": spd_dumps(),
        "serials": {k: (rd(f"/sys/class/dmi/id/{k}") or b"").decode().strip()
                    for k in ("product_serial", "board_serial", "product_uuid")},
    }
    sys.stdout.write("I " + json.dumps(info) + "\n")
    sys.stdout.flush()
    zones = rapl_zones()
    prev = {}
    while True:
        r, _, _ = select.select([sys.stdin], [], [], interval)
        if r and not sys.stdin.readline():
            return 0
        if os.getppid() != parent:
            return 0
        now = time.monotonic()
        out = {"power": {}, "vcore": {}}
        for d, (name, rng) in zones.items():
            e = rd(d + "/energy_uj")
            if not e:
                continue
            e = int(e)
            if d in prev:
                t0, e0 = prev[d]
                de = e - e0
                if de < 0 and rng:
                    de += rng
                if now > t0:
                    out["power"][name + ("" if d.count(":") == 1 else "") + "|" + d.rsplit("/", 1)[1]] = \
                        de / 1e6 / (now - t0)
            prev[d] = (now, e)
        for c in cpus:
            v = voltage(c, vend, fam, mod)
            if v is not None:
                out["vcore"][str(c)] = round(v, 4)
        sys.stdout.write("S " + json.dumps(out) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BrokenPipeError, KeyboardInterrupt):
        sys.exit(0)
