"""patch_partner.py -- the minimal, additive edits to the partners' root sheet.

SUPERSEDED: already applied, then restructure.py moved that page to sheets/analog.kicad_sch under a
sheet-boxes-only root. Kept as the record of exactly what was edited on the partners' page.

    python patch_partner.py

Text-level patch so every line we do not touch stays byte-identical. Backs the original up to
design/backup/ the first time. Edits:
  * ADS131M08 (U5) digital pins -> global labels (ADC_SCLK, ADC_DIN, ADC_DOUT, ADC_CS_N,
    ADC_DRDY_N, ADC_SYNC_RST, ADC_CLKIN); XTAL2 no-connect (external clock)
  * AVDD pin 27 wired to the +3.3V already on pin 15
  * REFIN -> C42 100 nF to GND (datasheet's internal-reference test condition)
  * AIN4P lifted off the unused-input ground strap -> global label PD_OUT (photodiode)
  * three sheet boxes for sheets/power, sheets/mcu, sheets/photodiode
NOT touched: C28-C30 (pin 1 floating) -- that is the partners' call.
"""
import shutil
import sys
from pathlib import Path

import ksch
from ksch import f, q, uid
from make_sheets import ROOT_UUID, SHEET_UUID, C_FP

SCH = Path("C:/Users/aidan/SSVEP_PCB/SSVEP_PCB/SSVEP_PCB.kicad_sch")
BACKUP = Path("C:/Users/aidan/SSVEP_PCB/design/backup/SSVEP_PCB.kicad_sch.orig")
PROJECT = "SSVEP_PCB"


def remove_block(lines, head, needle):
    """Delete the top-level `\\t(head` block whose text contains `needle`."""
    for i, line in enumerate(lines):
        if line.rstrip("\n") == f"\t({head}":
            j = i
            while lines[j].rstrip("\n") != "\t)":
                j += 1
            if any(needle in lines[k] for k in range(i, j + 1)):
                del lines[i:j + 1]
                return
    raise SystemExit(f"not found: {head} containing {needle!r} -- has the partners' sheet changed?")


def wire(a, b):
    return ["wire", ["pts", ["xy", f(a[0]), f(a[1])], ["xy", f(b[0]), f(b[1])]],
            ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(uid())]]


def glabel(name, p, angle, shape):
    just = "left" if angle == 0 else "right"
    return ["global_label", q(name), ["shape", shape], ["at", f(p[0]), f(p[1]), str(angle)],
            ["fields_autoplaced", "yes"], ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", just]],
            ["uuid", q(uid())],
            ["property", q("Intersheetrefs"), q("${INTERSHEET_REFS}"), ["at", f(p[0]), f(p[1]), "0"],
             ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", just], ["hide", "yes"]]]]


def symbol(lib_id, ref, value, x, y, footprint="", datasheet="", mpn="", ref_at=None, val_at=None,
           hide_ref=False, pins=("1", "2"), power=False):
    eff = lambda just=None, hide=False: (["effects", ["font", ["size", "1.27", "1.27"]]]
                                         + ([["justify", just]] if just else []) + ([["hide", "yes"]] if hide else []))
    rx, ry = ref_at or (x, y)
    vx, vy = val_at or (x, y)
    node = ["symbol", ["lib_id", q(lib_id)], ["at", f(x), f(y), "0"], ["unit", "1"],
            ["exclude_from_sim", "no"], ["in_bom", "no" if power else "yes"],
            ["on_board", "no" if power else "yes"], ["dnp", "no"], ["fields_autoplaced", "no"],
            ["uuid", q(uid())],
            ["property", q("Reference"), q(ref), ["at", f(rx), f(ry), "0"], eff("left", hide_ref)],
            ["property", q("Value"), q(value), ["at", f(vx), f(vy), "0"], eff("left")],
            ["property", q("Footprint"), q(footprint), ["at", f(x), f(y), "0"], eff(hide=True)],
            ["property", q("Datasheet"), q(datasheet), ["at", f(x), f(y), "0"], eff(hide=True)]]
    if mpn:
        node.append(["property", q("MPN"), q(mpn), ["at", f(x), f(y), "0"], eff(hide=True)])
    node += [["pin", q(n), ["uuid", q(uid())]] for n in pins]
    node.append(["instances", ["project", q(PROJECT), ["path", q("/" + ROOT_UUID), ["reference", q(ref)], ["unit", "1"]]]])
    return node


def sheet_box(name, file, x, y, page):
    w, h = 16.51, 10.16
    return ["sheet", ["at", f(x), f(y)], ["size", f(w), f(h)], ["exclude_from_sim", "no"],
            ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"], ["fields_autoplaced", "yes"],
            ["stroke", ["width", "0.1524"], ["type", "solid"]], ["fill", ["color", "0", "0", "0", "0.0000"]],
            ["uuid", q(SHEET_UUID[file])],
            ["property", q("Sheetname"), q(name), ["at", f(x), f(y - 0.7116), "0"],
             ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "bottom"]]],
            ["property", q("Sheetfile"), q(f"sheets/{file}.kicad_sch"), ["at", f(x), f(y + h + 0.5846), "0"],
             ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "top"], ["hide", "yes"]]],
            ["instances", ["project", q(PROJECT), ["path", q("/" + ROOT_UUID), ["page", q(page)]]]]]


def main():
    text = SCH.read_bytes().decode("utf-8")
    if "sheets/mcu.kicad_sch" in text:
        sys.exit("already patched")
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if not BACKUP.exists():
        shutil.copy2(SCH, BACKUP)
    lines = text.splitlines(keepends=True)

    # AIN4P off the ground strap: the dangling stub above it, the segment down to AIN4N, its junction
    remove_block(lines, "wire", "(xy 213.36 53.34) (xy 213.36 54.61)")
    remove_block(lines, "wire", "(xy 213.36 54.61) (xy 213.36 57.15)")
    remove_block(lines, "junction", "(at 213.36 54.61)")

    new = []
    # U5 right side: digital pins out to global labels (shape is from the ADC's point of view)
    for name, y, shape in (("ADC_CLKIN", 36.83, "input"), ("ADC_DIN", 57.15, "input"),
                           ("ADC_DOUT", 62.23, "output"), ("ADC_SCLK", 67.31, "input"),
                           ("ADC_DRDY_N", 72.39, "output"), ("ADC_CS_N", 77.47, "input"),
                           ("ADC_SYNC_RST", 82.55, "input")):
        new += [wire((264.16, y), (266.7, y)), glabel(name, (266.7, y), 0, shape)]
    new.append(["no_connect", ["at", "264.16", "44.45"], ["uuid", q(uid())]])          # XTAL2
    # AVDD pin 27 -> the +3.3V on pin 15 (junction at 213.36 87.63 already exists)
    new.append(wire((213.36, 85.09), (213.36, 87.63)))
    # REFIN -> C42 -> GND (the wire crosses the ground strap at x 209.55 without touching it)
    new.append(wire((213.36, 92.71), (203.2, 92.71)))
    new.append(symbol("Device:C", "C42", "100n", 203.2, 96.52, footprint=C_FP,
                      datasheet="https://product.samsungsem.com/mlcc/CL21B104KBCNNN.do", mpn="CL21B104KBCNNNC",
                      ref_at=(198.12, 95.885), val_at=(197.485, 98.425)))
    new.append(wire((203.2, 100.33), (203.2, 102.87)))
    new.append(symbol("power:GND", "#PWR0901", "GND", 203.2, 102.87, ref_at=(203.2, 109.22),
                      val_at=(201.93, 106.68), hide_ref=True, pins=("1",), power=True))
    # AIN4P -> photodiode
    new.append(wire((213.36, 54.61), (210.82, 54.61)))
    new.append(glabel("PD_OUT", (210.82, 54.61), 180, "input"))
    # our sheets
    new += [sheet_box("POWER", "power", 147.32, 57.15, "2"),
            sheet_box("MCU", "mcu", 166.37, 57.15, "3"),
            sheet_box("PHOTODIODE", "photodiode", 185.42, 57.15, "4")]

    at = next(i for i, l in enumerate(lines) if l.rstrip("\n") == "\t(sheet_instances")
    block = "".join("\t" + ksch.dump(n, 1) + "\n" for n in new)
    lines.insert(at, block)
    SCH.write_bytes("".join(lines).encode("utf-8"))
    print(f"patched {SCH.name}: removed 2 wires + 1 junction, added {len(new)} items; backup {BACKUP}")


if __name__ == "__main__":
    main()
