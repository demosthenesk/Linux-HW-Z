"""Build fake /sys + /proc trees for testing Linux HW-Z without the hardware.

  intel-laptop : 13th-gen Core i7-1355U (2P+8E), Iris Xe (i915), DDR4 SO-DIMM SPD, coretemp, dell_smm fan
  amd-desktop  : Ryzen 7 7700X + Radeon RX 6800 (amdgpu), DDR5 SPD, k10temp
  nvidia       : the AMD desktop with an RTX 4070 (nvidia driver; NVML from tests/fake_nvml.c)
"""

import os
import sys


def w(root, path, content, mode=None):
    p = root + path
    os.makedirs(os.path.dirname(p), exist_ok=True)
    data = content if isinstance(content, bytes) else (str(content) + "\n").encode()
    with open(p, "wb") as f:
        f.write(data)
    if mode is not None:
        os.chmod(p, mode)


def link(root, path, target):
    p = root + path
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if os.path.lexists(p):
        os.remove(p)
    os.symlink(target, p)


def cpuinfo(n, vendor, fam, model, step, brand, flags, mhz):
    out = []
    for i in range(n):
        out.append(f"processor\t: {i}\nvendor_id\t: {vendor}\ncpu family\t: {fam}\nmodel\t\t: {model}\n"
                   f"model name\t: {brand}\nstepping\t: {step}\nmicrocode\t: 0x4121\ncpu MHz\t\t: {mhz}\n"
                   f"flags\t\t: {flags}\nbogomips\t: 5222.40\naddress sizes\t: 39 bits physical, 48 bits virtual\n")
    return "\n".join(out)


def cache(root, cpu, idx, level, typ, size, ways, shared):
    b = f"/sys/devices/system/cpu/cpu{cpu}/cache/index{idx}"
    w(root, b + "/level", level)
    w(root, b + "/type", typ)
    w(root, b + "/size", size)
    w(root, b + "/ways_of_associativity", ways)
    w(root, b + "/coherency_line_size", 64)
    w(root, b + "/shared_cpu_list", shared)


def pcidev(root, slot, ven, dev, cls, sv=0, sd=0, rev=0, driver=None, extra=None):
    b = f"/sys/bus/pci/devices/{slot}"
    w(root, b + "/vendor", f"0x{ven:04x}")
    w(root, b + "/device", f"0x{dev:04x}")
    w(root, b + "/subsystem_vendor", f"0x{sv:04x}")
    w(root, b + "/subsystem_device", f"0x{sd:04x}")
    w(root, b + "/class", f"0x{cls:06x}")
    w(root, b + "/revision", f"0x{rev:02x}")
    if driver:
        link(root, b + "/driver", f"../../../bus/pci/drivers/{driver}")
    for k, v in (extra or {}).items():
        w(root, b + "/" + k, v)
    return b


def ddr4_spd():
    d = bytearray(512)
    d[0], d[1], d[2], d[3] = 0x23, 0x11, 0x0C, 0x03          # DDR4 SO-DIMM
    d[4] = 0x45  # 8Gb, 2 bank groups bits
    d[6] = 0x00
    d[11] = 0x03
    d[12] = 0x01  # x8, 1 rank
    d[13] = 0x03  # 64-bit
    d[17] = 0x00
    d[18] = 0x05  # tCK 0.625 ns -> 1600 MHz
    d[20], d[21], d[22], d[23] = 0x7A, 0xFF, 0x7F, 0x00     # CL 8..? (wide)
    d[24] = 0x6E  # tAA 13.75
    d[25] = 0x6E
    d[26] = 0x6E
    d[27] = 0x11
    d[28] = 0x00  # tRAS 0x100*0.125 = 32 ns
    d[29] = 0x6E  # tRC (0x100+0x6E)*0.125
    d[320], d[321] = 0x80, 0xAD                             # SK Hynix
    d[323], d[324] = 0x22, 0x15                             # 2022 week 15
    d[325:329] = bytes.fromhex("3A4B5C6D")
    d[329:349] = b"HMA81GS6DJR8N-XN    "
    d[350], d[351] = 0x80, 0xAD
    return bytes(d)


def ddr5_spd():
    d = bytearray(1024)
    d[0], d[1], d[2], d[3] = 0x30, 0x10, 0x12, 0x02         # DDR5 UDIMM
    d[4] = 0x04  # 16Gb, 1 die
    d[6] = 0x20  # x8
    d[20:22] = (417).to_bytes(2, "little")                  # tCK 0.417 ns -> 2400 MHz (DDR5-4800)
    d[24:29] = (0x1FFF).to_bytes(5, "little")     # CL20..44
    d[30:32] = (16000).to_bytes(2, "little")
    d[32:34] = (16000).to_bytes(2, "little")
    d[34:36] = (16000).to_bytes(2, "little")
    d[36:38] = (32000).to_bytes(2, "little")
    d[38:40] = (48000).to_bytes(2, "little")
    d[234] = 0x00  # 1 rank
    d[235] = 0x21  # 2 subchannels x 32 bit -> careful: bits[2:0]=1 -> 16? use 2 => 32-bit
    d[235] = 0x22
    d[512], d[513] = 0x80, 0xCE                             # Samsung
    d[515], d[516] = 0x23, 0x30
    d[517:521] = bytes.fromhex("01020304")
    d[521:551] = b"M323R2GA3BB0-CQKOD".ljust(30, b" ")
    d[552], d[553] = 0x80, 0xCE
    d[640], d[641] = 0x0C, 0x4A
    return bytes(d)


def intel_laptop(root):
    flags = ("fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ss ht "
             "lm pni pclmulqdq ssse3 fma cx16 sse4_1 sse4_2 movbe popcnt aes xsave avx f16c rdrand vmx avx2 bmi2 "
             "sha_ni avx_vnni")
    w(root, "/proc/cpuinfo", cpuinfo(12, "GenuineIntel", 6, 186, 3, "13th Gen Intel(R) Core(TM) i7-1355U", flags, 1200))
    w(root, "/sys/devices/system/cpu/online", "0-11")
    w(root, "/sys/devices/cpu_core/cpus", "0-3")
    w(root, "/sys/devices/cpu_atom/cpus", "4-11")
    for c in range(12):
        b = f"/sys/devices/system/cpu/cpu{c}"
        p = c < 4
        w(root, b + "/topology/physical_package_id", 0)
        w(root, b + "/topology/core_id", c // 2 * 4 if p else 8 + (c - 4))
        w(root, b + "/cpufreq/cpuinfo_max_freq", 5000000 if p else 3700000)
        w(root, b + "/cpufreq/cpuinfo_min_freq", 400000)
        w(root, b + "/cpufreq/base_frequency", 1700000 if p else 1200000)
        w(root, b + "/cpufreq/scaling_cur_freq", 2950000 + c * 1000 if p else 1800000 + c * 500)
        w(root, b + "/cpufreq/scaling_driver", "intel_pstate")
        w(root, b + "/cpufreq/scaling_governor", "powersave")
        if p:
            sib = f"{c // 2 * 2}-{c // 2 * 2 + 1}"
            cache(root, c, 0, 1, "Data", "48K", 12, sib)
            cache(root, c, 1, 1, "Instruction", "32K", 8, sib)
            cache(root, c, 2, 2, "Unified", "1280K", 10, sib)
        else:
            cl = "4-7" if c < 8 else "8-11"
            cache(root, c, 0, 1, "Data", "32K", 8, str(c))
            cache(root, c, 1, 1, "Instruction", "64K", 8, str(c))
            cache(root, c, 2, 2, "Unified", "2048K", 16, cl)
        cache(root, c, 3, 3, "Unified", "12288K", 12, "0-11")
    w(root, "/proc/stat", "cpu  1 2 3 4\n" + "".join(f"cpu{c} {100+c} 0 50 900 5 0 1 0\n" for c in range(12)))
    w(root, "/proc/meminfo", "MemTotal: 16107812 kB\nMemAvailable: 9123456 kB\nSwapTotal: 4194300 kB\nSwapFree: 4194300 kB")
    for k, v in {"sys_vendor": "Dell Inc.", "product_name": "Inspiron 15 3530", "product_version": "",
                 "board_vendor": "Dell Inc.", "board_name": "0JYKVJ", "board_version": "A00",
                 "bios_vendor": "Dell Inc.", "bios_version": "1.12.0", "bios_date": "06/12/2025",
                 "bios_release": "1.12", "chassis_type": "10", "product_family": "Inspiron"}.items():
        w(root, f"/sys/class/dmi/id/{k}", v)
    w(root, "/sys/firmware/efi/fw_platform_size", 64)
    pz = "/sys/class/powercap/intel-rapl:0"
    w(root, pz + "/name", "package-0")
    w(root, pz + "/constraint_0_power_limit_uw", 15000000)
    w(root, pz + "/constraint_0_max_power_uw", 15000000)
    pcidev(root, "0000:00:00.0", 0x8086, 0xA707, 0x060000, 0x1028, 0x0C11, 1)
    gb = pcidev(root, "0000:00:02.0", 0x8086, 0xA7A1, 0x030000, 0x1028, 0x0C11, 4, "i915",
                {"boot_vga": 1})
    os.makedirs(root + gb + "/drm/card1", exist_ok=True)
    os.makedirs(root + gb + "/drm/renderD128", exist_ok=True)
    card = "/sys/class/drm/card1"
    for k, v in {"gt_act_freq_mhz": 700, "gt_cur_freq_mhz": 700, "gt_max_freq_mhz": 1500,
                 "gt_RP0_freq_mhz": 1500, "gt_RP1_freq_mhz": 300, "gt_RPn_freq_mhz": 100,
                 "power/rc6_residency_ms": 123456}.items():
        w(root, f"{card}/{k}", v)
    pcidev(root, "0000:00:1f.0", 0x8086, 0x519D, 0x060100, 0x1028, 0x0C11, 1)
    pcidev(root, "0000:00:1c.0", 0x8086, 0x51BB, 0x060400, 0, 0, 1, "pcieport",
           {"max_link_speed": "16.0 GT/s PCIe", "max_link_width": 4, "current_link_speed": "16.0 GT/s PCIe",
            "current_link_width": 4})
    h = "/sys/class/hwmon/hwmon3"
    w(root, h + "/name", "coretemp")
    w(root, h + "/temp1_input", 52000)
    w(root, h + "/temp1_label", "Package id 0")
    for i in range(2, 8):
        w(root, h + f"/temp{i}_input", 45000 + i * 1000)
        w(root, h + f"/temp{i}_label", f"Core {i - 2}")
    h = "/sys/class/hwmon/hwmon5"
    w(root, h + "/name", "dell_smm")
    w(root, h + "/fan1_input", 2380)
    w(root, h + "/fan1_label", "Processor Fan")
    h = "/sys/class/hwmon/hwmon2"
    w(root, h + "/name", "nvme")
    w(root, h + "/temp1_input", 38850)
    w(root, h + "/temp1_label", "Composite")
    w(root, "/sys/bus/i2c/drivers/ee1004/0-0050/eeprom", ddr4_spd())


def amd_desktop(root, nvidia=False):
    flags = ("fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ht lm "
             "pni pclmulqdq ssse3 fma cx16 sse4_1 sse4_2 movbe popcnt aes xsave avx f16c rdrand svm sse4a avx2 "
             "bmi2 sha_ni avx512f avx512bw avx512vl avx512_vnni avx512_bf16")
    w(root, "/proc/cpuinfo", cpuinfo(16, "AuthenticAMD", 25, 97, 2, "AMD Ryzen 7 7700X 8-Core Processor", flags, 4500))
    w(root, "/sys/devices/system/cpu/online", "0-15")
    for c in range(16):
        b = f"/sys/devices/system/cpu/cpu{c}"
        w(root, b + "/topology/physical_package_id", 0)
        w(root, b + "/topology/core_id", c % 8)
        w(root, b + "/cpufreq/cpuinfo_max_freq", 5573000)
        w(root, b + "/cpufreq/cpuinfo_min_freq", 545000)
        w(root, b + "/cpufreq/amd_pstate_nominal_freq", 4500000)
        w(root, b + "/cpufreq/scaling_cur_freq", 4400000 + c * 9000)
        w(root, b + "/cpufreq/scaling_driver", "amd-pstate-epp")
        sib = f"{c % 8},{c % 8 + 8}"
        cache(root, c, 0, 1, "Data", "32K", 8, sib)
        cache(root, c, 1, 1, "Instruction", "32K", 8, sib)
        cache(root, c, 2, 2, "Unified", "1024K", 8, sib)
        cache(root, c, 3, 3, "Unified", "32768K", 16, "0-15")
    w(root, "/proc/stat", "cpu  1 2 3 4\n" + "".join(f"cpu{c} {100+c} 0 50 900 5 0 1 0\n" for c in range(16)))
    w(root, "/proc/meminfo", "MemTotal: 32604020 kB\nMemAvailable: 25123456 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB")
    for k, v in {"sys_vendor": "Micro-Star International Co., Ltd.", "product_name": "MS-7E26",
                 "board_vendor": "Micro-Star International Co., Ltd.", "board_name": "MAG B650 TOMAHAWK WIFI (MS-7D75)",
                 "board_version": "1.0", "bios_vendor": "American Megatrends International, LLC.",
                 "bios_version": "1.A0", "bios_date": "08/22/2024", "chassis_type": "3"}.items():
        w(root, f"/sys/class/dmi/id/{k}", v)
    pcidev(root, "0000:00:00.0", 0x1022, 0x14D8, 0x060000, 0x1022, 0x14D8)
    pcidev(root, "0000:00:14.3", 0x1022, 0x790E, 0x060100, 0x1462, 0x7D75, 0x51)
    pcidev(root, "0000:00:01.1", 0x1022, 0x14DB, 0x060400, 0, 0, 0, "pcieport",
           {"max_link_speed": "32.0 GT/s PCIe", "max_link_width": 16, "current_link_speed": "16.0 GT/s PCIe",
            "current_link_width": 16})
    if nvidia:
        gb = pcidev(root, "0000:01:00.0", 0x10DE, 0x2786, 0x030000, 0x1043, 0x88EE, 0xA1, "nvidia",
                    {"boot_vga": 1, "max_link_speed": "16.0 GT/s PCIe", "max_link_width": 16,
                     "current_link_speed": "2.5 GT/s PCIe", "current_link_width": 16})
        os.makedirs(root + gb + "/drm/card0", exist_ok=True)
        os.makedirs(root + gb + "/drm/renderD128", exist_ok=True)
        w(root, "/sys/module/nvidia/version", "560.35.03")
    else:
        gb = pcidev(root, "0000:03:00.0", 0x1002, 0x73BF, 0x030000, 0x1DA2, 0xE438, 0xC3, "amdgpu",
                    {"boot_vga": 1, "max_link_speed": "16.0 GT/s PCIe", "max_link_width": 16,
                     "current_link_speed": "16.0 GT/s PCIe", "current_link_width": 16,
                     "vbios_version": "113-D4120100-100", "mem_info_vram_total": 17163091968,
                     "mem_info_vis_vram_total": 268435456, "mem_info_vram_used": 1234567168,
                     "mem_info_gtt_total": 16000000000, "mem_info_gtt_used": 50000000,
                     "mem_info_vram_vendor": "samsung", "gpu_busy_percent": 37, "mem_busy_percent": 12,
                     "pp_dpm_sclk": "0: 500Mhz\n1: 1815Mhz *\n2: 2475Mhz",
                     "pp_dpm_mclk": "0: 96Mhz\n1: 456Mhz\n2: 673Mhz\n3: 1000Mhz *"})
        os.makedirs(root + gb + "/drm/card0", exist_ok=True)
        os.makedirs(root + gb + "/drm/renderD128", exist_ok=True)
        h = gb + "/hwmon/hwmon4"
        for k, v in {"name": "amdgpu", "temp1_input": 54000, "temp1_label": "edge", "temp2_input": 71000,
                     "temp2_label": "junction", "temp3_input": 68000, "temp3_label": "mem",
                     "power1_average": 121000000, "power1_cap": 203000000, "fan1_input": 1270, "pwm1": 90,
                     "in0_input": 906, "freq1_input": 1815000000, "freq2_input": 1000000000}.items():
            w(root, f"{h}/{k}", v)
        link(root, "/sys/class/hwmon/hwmon4", "../../bus/pci/devices/0000:03:00.0/hwmon/hwmon4")
    h = "/sys/class/hwmon/hwmon1"
    w(root, h + "/name", "k10temp")
    w(root, h + "/temp1_input", 61250)
    w(root, h + "/temp1_label", "Tctl")
    w(root, h + "/temp3_input", 55000)
    w(root, h + "/temp3_label", "Tccd1")
    w(root, "/sys/bus/i2c/drivers/spd5118/1-0051/eeprom", ddr5_spd())
    w(root, "/sys/bus/i2c/drivers/spd5118/1-0053/eeprom", ddr5_spd())


if __name__ == "__main__":
    kind, root = sys.argv[1], sys.argv[2]
    os.makedirs(root, exist_ok=True)
    {"intel-laptop": intel_laptop, "amd-desktop": amd_desktop,
     "nvidia": lambda r: amd_desktop(r, nvidia=True)}[kind](root)
    print("ok", root)
