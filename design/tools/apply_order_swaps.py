"""apply_order_swaps.py -- the part swaps for the 2026-11-02 DigiKey order, on the sheets and the boards.

    python apply_order_swaps.py

DigiKey's live stock (2026-11-02) had five of the board's parts at zero. The three ICs the partners
already bought (INA333AIDGKR, MCP6002-I/SN, ADS131M08IPBS) stay; the rest are swapped for stocked
parts with the same footprint and pinout:

    TPS7A2033PDBVR   -> LP5907MFX-3.3/NOPB    U101: same DBV pinout (IN 1, GND 2, EN 3, NC 4, OUT 5),
                                              EN held low by an internal 1M, 1u in and out
    SI2301CDS-T1-GE3 -> SI2301CDS-T1-BE3      Q101: the same FET from Vishay's other fab
    CL21B105KBFVPJE  -> CL21B105KAFNNNE       every 1u: 25 V X7R instead of 50 V (rails are <= 5 V)
    0805YD106KAT2A   -> C2012X5R1E106K125AB   C6: TDK 10u 25 V X5R instead of 16 V

and the partners' resistors, which carried a value only, get Yageo RC0805FR-07 (1 % thick film)
part numbers so the BOM can be ordered. Fields are changed where they exist and added (hidden)
where they do not, on every symbol and footprint whose MPN or value matches -- refs are not
listed, so a part added later with an old MPN is caught too. The symbol library rename
(SSVEP:TPS7A2033PDBVR -> SSVEP:LP5907MFX-3.3) covers the sheet's embedded copy; gen_symbols.py
makes the library. Bytes in, bytes out; backup in design/backup/pre_order_swaps/ (taken by hand).
"""
import re
import uuid
from pathlib import Path

import ksch
from ksch import f, q

ROOT = Path("C:/Users/aidan/SSVEP_PCB/SSVEP_PCB")
SHEETS = [ROOT / "sheets" / n for n in ("power.kicad_sch", "mcu.kicad_sch", "photodiode.kicad_sch",
                                         "analog.kicad_sch")]
BOARDS = [ROOT / n for n in ("SSVEP_PCB.kicad_pcb", "SSVEP_PCB_auto.kicad_pcb", "SSVEP_PCB_manual.kicad_pcb")]

SAM = "Samsung Electro-Mechanics"
SWAP = {  # old MPN -> fields to set ("Voltage Rating" only where the part already has one)
    "TPS7A2033PDBVR": {"Value": "LP5907MFX-3.3", "MPN": "LP5907MFX-3.3/NOPB",
                       "Manufacturer": "Texas Instruments", "DigiKey_PN": "296-38557-1-ND",
                       "Datasheet": "https://www.ti.com/lit/gpn/lp5907"},
    "SI2301CDS-T1-GE3": {"MPN": "SI2301CDS-T1-BE3", "DigiKey_PN": "742-SI2301CDS-T1-BE3CT-ND"},
    "CL21B105KBFVPJE": {"MPN": "CL21B105KAFNNNE", "Manufacturer": SAM, "DigiKey_PN": "1276-1066-1-ND",
                        "Datasheet": "https://product.samsungsem.com/mlcc/CL21B105KAFNNN.do",
                        "Voltage Rating": "25V"},
    "0805YD106KAT2A": {"MPN": "C2012X5R1E106K125AB", "Manufacturer": "TDK Corporation",
                       "DigiKey_PN": "445-5984-1-ND",
                       "Datasheet": "https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=C2012X5R1E106K125AB",
                       "Voltage Rating": "25V"},
}
OPTIONAL = {"Voltage Rating"}
R_DS = "https://yageogroup.com/content/Resource%20Library/Datasheet/PYU-RC_GROUP_51_ROHS_L.pdf"
RES = {  # value -> (MPN, DigiKey cut tape)
    "47": ("RC0805FR-0747RL", "311-47.0CRCT-ND"), "100": ("RC0805FR-07100RL", "311-100CRCT-ND"),
    "3.3k": ("RC0805FR-073K3L", "311-3.30KCRCT-ND"), "4.7k": ("RC0805FR-074K7L", "311-4.70KCRCT-ND"),
    "39k": ("RC0805FR-0739KL", "311-39.0KCRCT-ND"), "300k": ("RC0805FR-07300KL", "311-300KCRCT-ND"),
    "390k": ("RC0805FR-07390KL", "311-390KCRCT-ND"), "1M": ("RC0805FR-071ML", "311-1.00MCRCT-ND"),
}
TEXT = [  # whole-file replacements, after the fields
    ('"SSVEP:TPS7A2033PDBVR"', '"SSVEP:LP5907MFX-3.3"'),
    ('"TPS7A2033PDBVR_', '"LP5907MFX-3.3_'),
    ('"TPS7A2033PDBVR"', '"LP5907MFX-3.3"'),
    ("https://www.ti.com/lit/gpn/tps7a20", "https://www.ti.com/lit/gpn/lp5907"),
    ("TPS7A20 300 mA ultra-low-noise LDO", "LP5907 250 mA ultra-low-noise LDO"),
    ("No switching regulator: TPS7A20, 7 uVrms", "No switching regulator: LP5907, 10 uVrms"),
    ("worst case of the TPS7A20's 300 mA", "worst case of the LP5907's 250 mA"),
]


def wanted(props: dict) -> dict:
    """The fields this part should end up with, or {} to leave it alone."""
    if props.get("MPN") in SWAP:
        return {k: v for k, v in SWAP[props["MPN"]].items() if k not in OPTIONAL or k in props}
    if props.get("Reference", "").startswith("R") and not props.get("MPN") and props.get("Value") in RES:
        mpn, dk = RES[props["Value"]]
        return {"Manufacturer": "YAGEO", "MPN": mpn, "DigiKey_PN": dk, "Datasheet": R_DS}
    return {}


def sheet_prop(name, value, x, y, nl):
    node = ["property", q(name), q(value), ["at", f(x), f(y), "0"],
            ["effects", ["font", ["size", "1.27", "1.27"]], ["hide", "yes"]]]
    return "\t\t" + ksch.dump(node, 2).replace("\n", nl) + nl


def board_prop(name, value, nl):
    return nl.join(["\t\t(property " + q(name) + " " + q(value), "\t\t\t(at 0 0 0)", '\t\t\t(layer "F.Fab")',
                    "\t\t\t(hide yes)", f'\t\t\t(uuid "{uuid.uuid4()}")', "\t\t\t(effects",
                    "\t\t\t\t(font", "\t\t\t\t\t(size 1 1)", "\t\t\t\t\t(thickness 0.15)", "\t\t\t\t)",
                    "\t\t\t)", "\t\t)"]) + nl


def apply(path: Path, opener: str, before: str, board: bool, log: list):
    raw = path.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.splitlines(keepends=True)
    out, i = [], 0
    while i < len(lines):
        if not (lines[i].rstrip("\r\n") + " ").startswith(opener + " "):
            out.append(lines[i]); i += 1; continue
        j = i
        while lines[j].rstrip("\r\n") != "\t)":
            j += 1
        block = "".join(lines[i:j + 1])
        props = dict(re.findall(r'^\t\t\(property "([^"]+)" "([^"]*)"', block, re.M))
        want = wanted(props)
        if want:
            missing = []
            for name, value in want.items():
                pat = re.compile(r'(^\t\t\(property "' + re.escape(name) + r'" )"[^"]*"', re.M)
                if pat.search(block):
                    block = pat.sub(lambda m: m.group(1) + q(value), block, count=1)
                else:
                    missing.append((name, value))
            if missing:
                if board:
                    add = "".join(board_prop(n, v, nl) for n, v in missing)
                else:
                    at = re.search(r'^\t\t\(at ([-\d.]+) ([-\d.]+)', block, re.M)
                    add = "".join(sheet_prop(n, v, float(at.group(1)), float(at.group(2)), nl) for n, v in missing)
                k = block.index(before)
                block = block[:k] + add + block[k:]
            log.append(f"  {path.name:<28} {props.get('Reference'):<5} {props.get('MPN') or props.get('Value'):<18}"
                       f" -> {want['MPN']}")
        out.append(block)
        i = j + 1
    text = "".join(out)
    for old, new in TEXT:
        text = text.replace(old, new)
    if text != raw:
        path.write_bytes(text.encode("utf-8"))


def main():
    log = []
    for p in SHEETS:
        apply(p, "\t(symbol", "\t\t(pin ", False, log)
    for p in BOARDS:
        apply(p, "\t(footprint", "\t\t(path ", True, log)
    print("\n".join(log))
    left = [str(p.name) for p in SHEETS + BOARDS
            if re.search(r"TPS7A2033|SI2301CDS-T1-GE3|CL21B105KBFVPJE|0805YD106KAT2A", p.read_text(encoding="utf-8"))]
    print("old part numbers left in:", left or "none")


if __name__ == "__main__":
    main()
