"""CPU code names and process technology by (vendor, family, model).

The table covers the common desktop, laptop and server parts of the last
fifteen years.  Unknown models simply show no code name.
"""

from __future__ import annotations

# Intel family 6: model -> (code name, technology)
INTEL_6 = {
    0x1A: ("Bloomfield", "45 nm"), 0x1E: ("Lynnfield", "45 nm"), 0x1F: ("Havendale", "45 nm"),
    0x2E: ("Beckton", "45 nm"), 0x25: ("Clarkdale/Arrandale", "32 nm"), 0x2C: ("Gulftown", "32 nm"),
    0x2F: ("Westmere-EX", "32 nm"), 0x2A: ("Sandy Bridge", "32 nm"), 0x2D: ("Sandy Bridge-E", "32 nm"),
    0x3A: ("Ivy Bridge", "22 nm"), 0x3E: ("Ivy Bridge-E", "22 nm"), 0x3C: ("Haswell", "22 nm"),
    0x45: ("Haswell-ULT", "22 nm"), 0x46: ("Crystal Well", "22 nm"), 0x3F: ("Haswell-E", "22 nm"),
    0x3D: ("Broadwell-U", "14 nm"), 0x47: ("Broadwell-H", "14 nm"), 0x4F: ("Broadwell-E", "14 nm"),
    0x56: ("Broadwell-DE", "14 nm"), 0x4E: ("Skylake-U/Y", "14 nm"), 0x5E: ("Skylake-S/H", "14 nm"),
    0x55: ("Skylake-SP", "14 nm"), 0x8E: ("Kaby Lake-U", "14 nm"), 0x9E: ("Kaby Lake", "14 nm"),
    0xA5: ("Comet Lake", "14 nm"), 0xA6: ("Comet Lake-U", "14 nm"), 0x66: ("Cannon Lake", "10 nm"),
    0x7D: ("Ice Lake", "10 nm"), 0x7E: ("Ice Lake-U/Y", "10 nm"), 0x6A: ("Ice Lake-SP", "10 nm"),
    0x6C: ("Ice Lake-D", "10 nm"), 0x8C: ("Tiger Lake-UP3", "10 nm SuperFin"),
    0x8D: ("Tiger Lake-H", "10 nm SuperFin"), 0xA7: ("Rocket Lake", "14 nm"),
    0x97: ("Alder Lake-S", "Intel 7"), 0x9A: ("Alder Lake-P", "Intel 7"),
    0xBE: ("Alder Lake-N", "Intel 7"), 0xB7: ("Raptor Lake-S", "Intel 7"),
    0xBA: ("Raptor Lake-P", "Intel 7"), 0xBF: ("Raptor Lake-S", "Intel 7"),
    0xAA: ("Meteor Lake", "Intel 4"), 0xAC: ("Meteor Lake", "Intel 4"),
    0xB5: ("Arrow Lake-U", "Intel 3"), 0xC5: ("Arrow Lake-H", "TSMC N3B"),
    0xC6: ("Arrow Lake-S", "TSMC N3B"), 0xBD: ("Lunar Lake", "TSMC N3B"),
    0xCC: ("Panther Lake", "Intel 18A"), 0x8F: ("Sapphire Rapids", "Intel 7"),
    0xCF: ("Emerald Rapids", "Intel 7"), 0xAD: ("Granite Rapids", "Intel 3"),
    0xAE: ("Granite Rapids-D", "Intel 3"), 0xAF: ("Sierra Forest", "Intel 3"),
    0xDD: ("Clearwater Forest", "Intel 18A"),
    # Atom / low power
    0x37: ("Bay Trail", "22 nm"), 0x4C: ("Cherry Trail/Braswell", "14 nm"), 0x5C: ("Apollo Lake", "14 nm"),
    0x5F: ("Denverton", "14 nm"), 0x7A: ("Gemini Lake", "14 nm"), 0x86: ("Snow Ridge", "10 nm"),
    0x96: ("Elkhart Lake", "10 nm"), 0x9C: ("Jasper Lake", "10 nm"), 0x8A: ("Lakefield", "10 nm"),
}

# Steppings that change the name within one model.
INTEL_6_STEP = {
    (0x55, 5): ("Cascade Lake-SP", "14 nm"), (0x55, 6): ("Cascade Lake-SP", "14 nm"),
    (0x55, 7): ("Cascade Lake-SP", "14 nm"), (0x55, 11): ("Cooper Lake", "14 nm"),
    (0x8E, 10): ("Coffee Lake-U", "14 nm"), (0x8E, 11): ("Whiskey Lake-U", "14 nm"),
    (0x8E, 12): ("Comet Lake-U", "14 nm"), (0x9E, 10): ("Coffee Lake", "14 nm"),
    (0x9E, 11): ("Coffee Lake", "14 nm"), (0x9E, 12): ("Coffee Lake Refresh", "14 nm"),
    (0x9E, 13): ("Coffee Lake Refresh", "14 nm"),
}

# AMD: (family, model) -> (code name, technology).  Ranges are expanded below.
_AMD_RANGES = [
    (0x17, 0x00, 0x0F, "Summit Ridge / Naples", "14 nm"),
    (0x17, 0x10, 0x17, "Raven Ridge", "14 nm"),
    (0x17, 0x18, 0x1F, "Picasso", "12 nm"),
    (0x17, 0x20, 0x2F, "Dali / Pollock", "14 nm"),
    (0x17, 0x30, 0x3F, "Rome / Castle Peak", "7 nm"),
    (0x17, 0x60, 0x67, "Renoir", "7 nm"),
    (0x17, 0x68, 0x6F, "Lucienne", "7 nm"),
    (0x17, 0x70, 0x7F, "Matisse", "7 nm"),
    (0x17, 0x90, 0x9F, "Van Gogh", "7 nm"),
    (0x17, 0xA0, 0xAF, "Mendocino", "6 nm"),
    (0x19, 0x00, 0x0F, "Milan", "7 nm"),
    (0x19, 0x10, 0x1F, "Genoa", "5 nm"),
    (0x19, 0x20, 0x2F, "Vermeer", "7 nm"),
    (0x19, 0x40, 0x4F, "Rembrandt", "6 nm"),
    (0x19, 0x50, 0x5F, "Cezanne / Barcelo", "7 nm"),
    (0x19, 0x60, 0x6F, "Raphael", "5 nm"),
    (0x19, 0x70, 0x77, "Phoenix / Hawk Point", "4 nm"),
    (0x19, 0x78, 0x7F, "Phoenix 2", "4 nm"),
    (0x19, 0xA0, 0xAF, "Bergamo / Siena", "5 nm"),
    (0x1A, 0x00, 0x1F, "Turin", "4 nm / 3 nm"),
    (0x1A, 0x20, 0x2F, "Strix Point / Krackan Point", "4 nm"),
    (0x1A, 0x40, 0x4F, "Granite Ridge", "4 nm"),
    (0x1A, 0x60, 0x6F, "Shimada Peak", "4 nm"),
    (0x1A, 0x70, 0x7F, "Strix Halo", "4 nm"),
]
AMD = {}
for fam, lo, hi, name, tech in _AMD_RANGES:
    for m in range(lo, hi + 1):
        AMD[(fam, m)] = (name, tech)
# a few exact models inside the ranges
AMD[(0x17, 0x08)] = ("Pinnacle Ridge", "12 nm")
AMD[(0x17, 0x71)] = ("Matisse", "7 nm")
AMD[(0x19, 0x08)] = ("Chagall", "7 nm")
AMD[(0x19, 0x44)] = ("Rembrandt-R", "6 nm")

AMD_FAMILY_NAMES = {
    0x10: ("K10", "45 nm"), 0x12: ("Llano", "32 nm"), 0x14: ("Bobcat", "40 nm"),
    0x15: ("Bulldozer family", "32/28 nm"), 0x16: ("Jaguar/Puma", "28 nm"),
    0x17: ("Zen / Zen 2", ""), 0x19: ("Zen 3 / Zen 4", ""), 0x1A: ("Zen 5", ""),
}


def lookup(vendor: str, family: int, model: int, stepping: int) -> tuple[str, str]:
    if vendor == "GenuineIntel" and family == 6:
        hit = INTEL_6_STEP.get((model, stepping)) or INTEL_6.get(model)
        return hit or ("", "")
    if vendor in ("AuthenticAMD", "HygonGenuine"):
        hit = AMD.get((family, model))
        if hit:
            return hit
        return AMD_FAMILY_NAMES.get(family, ("", ""))
    return "", ""
