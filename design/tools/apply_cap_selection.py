"""apply_cap_selection.py -- the capacitor part selection and value changes on the partners' page.

    python apply_cap_selection.py

For every capacitor on sheets/analog.kicad_sch: set Value (where it changes), Datasheet, and add
hidden fields Manufacturer, MPN, DigiKey_PN, Voltage Rating, Capacitor Type. Value changes:
input coupling C2/C4/C10/C18/C20 0.47u -> 0.15u (film; HPF 0.34 Hz -> ~1 Hz) and output filter
C9/C11/C13/C15/C21/C22/C23/C24 390n -> 150n (two loaded RC stages ~47 Hz -> ~120 Hz).
All 0805, so the partners' footprints and layout are unchanged. Stock is the catalogue's DigiKey
snapshot (2026-07). Bytes in, bytes out; backup to design/backup/pre_caps/ first.
"""
import re
import shutil
from pathlib import Path

import ksch
from ksch import f, q

SHEET = Path("C:/Users/aidan/SSVEP_PCB/SSVEP_PCB/sheets/analog.kicad_sch")
BACKUP = Path("C:/Users/aidan/SSVEP_PCB/design/backup/pre_caps")

SAM = "Samsung Electro-Mechanics"
PARTS = {  # key -> (value, manufacturer, mpn, digikey_pn, datasheet, voltage rating, type)
    "film150n": ("0.15u", "Rubycon", "35MF154KZ22012", "1189-35MF154KZ22012CT-ND",
                 "https://www.rubycon.co.jp/wp-content/uploads/catalog-pmlcap/MF.pdf", "35V", "Film"),
    "x7r150n": ("150n", "KYOCERA AVX", "KGM21ER71H154KU", "478-KGM21ER71H154KUCT-ND",
                "https://datasheets.kyocera-avx.com/KGM_X7R.pdf", "50V", "Ceramic"),
    "c0g1n": ("1n", SAM, "CL21C102JBC1PNC", "1276-2575-1-ND",
              "https://product.samsungsem.com/mlcc/CL21C102JBC1PN.do", "50V", "Ceramic"),
    "c0g10n": ("10n", SAM, "CL21C103JBF1PNE", "1276-6790-1-ND",
               "https://product.samsungsem.com/mlcc/CL21C103JBF1PN.do", "50V", "Ceramic"),
    "x7r100n": ("100n", SAM, "CL21B104KBCNNNC", "1276-1003-1-ND",
                "https://product.samsungsem.com/mlcc/CL21B104KBCNNN.do", "50V", "Ceramic"),
    "x7r1u": ("1u", SAM, "CL21B105KAFNNNE", "1276-1066-1-ND",
              "https://product.samsungsem.com/mlcc/CL21B105KAFNNN.do", "25V", "Ceramic"),
    "x7r220n": ("220n", SAM, "CL21B224KBFVPNE", "1276-7012-1-ND",
                "https://product.samsungsem.com/mlcc/CL21B224KBFVPN.do", "50V", "Ceramic"),
    "x5r10u": ("10u", "TDK Corporation", "C2012X5R1E106K125AB", "445-5984-1-ND",
               "https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=C2012X5R1E106K125AB", "25V", "Ceramic"),
}
SELECTION = {
    **{r: "film150n" for r in ("C2", "C4", "C10", "C18", "C20")},
    **{r: "x7r150n" for r in ("C9", "C11", "C13", "C15", "C21", "C22", "C23", "C24")},
    **{r: "c0g1n" for r in ("C1", "C3", "C7", "C12", "C14")},
    **{r: "c0g10n" for r in ("C5", "C8", "C16", "C17", "C19")},
    **{r: "x7r100n" for r in ("C25", "C27", "C28", "C29", "C30", "C31", "C32", "C33", "C34",
                              "C36", "C37", "C38", "C39", "C40", "C42")},
    **{r: "x7r1u" for r in ("C26", "C41")},
    "C35": "x7r220n",
    "C6": "x5r10u",
}
EXPECT_OLD = {"film150n": ".47u", "x7r150n": "390n"}      # refuse to change a value we did not expect


def prop_line(name, value, x, y, nl):
    node = ["property", q(name), q(value), ["at", f(x), f(y), "0"],
            ["effects", ["font", ["size", "1.27", "1.27"]], ["hide", "yes"]]]
    return "\t\t" + ksch.dump(node, 2).replace("\n", nl) + nl


def main():
    BACKUP.mkdir(parents=True, exist_ok=True)
    if not (BACKUP / SHEET.name).exists():
        shutil.copy2(SHEET, BACKUP / SHEET.name)
    raw = SHEET.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.splitlines(keepends=True)
    out, i, done = [], 0, {}
    while i < len(lines):
        if lines[i].rstrip("\r\n") != "\t(symbol":
            out.append(lines[i]); i += 1; continue
        j = i
        while lines[j].rstrip("\r\n") != "\t)":
            j += 1
        block = lines[i:j + 1]
        text = "".join(block)
        m = re.search(r'\(property "Reference" "([^"]+)"', text)
        ref = m.group(1) if m else ""
        if ref in SELECTION and ref not in done:
            value, mfr, mpn, dk, ds, volts, kind = PARTS[SELECTION[ref]]
            at = re.search(r'^\t\t\(at ([-\d.]+) ([-\d.]+)', text, re.M)
            x, y = float(at.group(1)), float(at.group(2))
            new, inserted = [], False
            for line in block:
                mv = re.match(r'(\t\t\(property "Value" )"([^"]*)"(.*)', line, re.S)
                md = re.match(r'(\t\t\(property "Datasheet" )"([^"]*)"(.*)', line, re.S)
                if mv:
                    old = mv.group(2)
                    want = EXPECT_OLD.get(SELECTION[ref])
                    if want and old != want:
                        raise SystemExit(f"{ref}: value is {old!r}, expected {want!r} -- sheet changed?")
                    line = f'{mv.group(1)}"{value}"{mv.group(3)}'
                    done[ref] = (old, value, mpn)
                elif md:
                    line = f'{md.group(1)}"{ds}"{md.group(3)}'
                elif not inserted and line.startswith("\t\t(pin "):
                    for name, val in (("Manufacturer", mfr), ("MPN", mpn), ("DigiKey_PN", dk),
                                      ("Voltage Rating", volts), ("Capacitor Type", kind)):
                        new.append(prop_line(name, val, x, y, nl))
                    inserted = True
                new.append(line)
            block = new
        out += block
        i = j + 1
    missing = sorted(set(SELECTION) - set(done))
    if missing:
        raise SystemExit(f"not found on the sheet: {missing}")
    SHEET.write_bytes("".join(out).encode("utf-8"))
    changed = {r: v for r, v in done.items() if v[0] != v[1]}
    print(f"{len(done)} capacitors given part fields; values changed on {len(changed)}:")
    for r, (old, new, mpn) in sorted(changed.items(), key=lambda k: int(k[0][1:])):
        print(f"  {r}: {old} -> {new}  ({mpn})")


if __name__ == "__main__":
    main()
