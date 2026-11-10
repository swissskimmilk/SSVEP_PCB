"""restructure.py -- a root page that is only sheet boxes; the partners' page becomes ANALOG.

    python restructure.py

Before: SSVEP_PCB.kicad_sch was the partners' circuit (with our three sheet boxes squeezed in).
After:  SSVEP_PCB.kicad_sch  root: four sheet boxes and a title, nothing else
        sheets/analog.kicad_sch    the partners' page, every line as it was except
                                   - our three sheet boxes and sheet_instances (root-only) removed
                                   - its own file uuid
                                   - each symbol's instance path now runs through the ANALOG box
The root keeps its uuid, so our sheets' instance paths are unchanged. The PCB's 88 footprints
are re-pathed to the same symbols under /ANALOG/ so nothing is orphaned. Text-level edits on
bytes: line endings and every untouched line stay exactly as they were. Backups go to
design/backup/pre_restructure/ the first time.
"""
import re
import shutil
import sys
from pathlib import Path

import ksch
from ksch import f, q
from make_sheets import ROOT_UUID, SHEET_UUID

PROJ = Path("C:/Users/aidan/SSVEP_PCB/SSVEP_PCB")
ROOT, PCB = PROJ / "SSVEP_PCB.kicad_sch", PROJ / "SSVEP_PCB.kicad_pcb"
ANALOG = PROJ / "sheets" / "analog.kicad_sch"
BACKUP = Path("C:/Users/aidan/SSVEP_PCB/design/backup/pre_restructure")
ANALOG_SHEET = "5f0c3a5e-1d6b-4f1e-9b7a-3c2e8d4a1000"     # the ANALOG box on the new root
ANALOG_FILE_UUID = "5f0c3a5e-1d6b-4f1e-9b7a-3c2e8d4a10f0"
PROJECT = "SSVEP_PCB"


def drop_blocks(lines, head):
    """Remove every top-level `\\t(head` block."""
    out, i = [], 0
    while i < len(lines):
        if lines[i].rstrip("\r\n") == f"\t({head}":
            while lines[i].rstrip("\r\n") != "\t)":
                i += 1
            i += 1
            continue
        out.append(lines[i])
        i += 1
    return out


def analog_page(text: str) -> str:
    lines = drop_blocks(drop_blocks(text.splitlines(keepends=True), "sheet"), "sheet_instances")
    body = "".join(lines)
    body = body.replace(f'(uuid "{ROOT_UUID}")', f'(uuid "{ANALOG_FILE_UUID}")', 1)
    n = body.count(f'(path "/{ROOT_UUID}"')
    body = body.replace(f'(path "/{ROOT_UUID}"', f'(path "/{ROOT_UUID}/{ANALOG_SHEET}"')
    print(f"  analog page: {n} symbol instance paths moved under the ANALOG box")
    return body


def sheet_box(name, file, uid, x, y, w, h, page):
    return ["sheet", ["at", f(x), f(y)], ["size", f(w), f(h)], ["exclude_from_sim", "no"],
            ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"], ["fields_autoplaced", "yes"],
            ["stroke", ["width", "0.1524"], ["type", "solid"]], ["fill", ["color", "0", "0", "0", "0.0000"]],
            ["uuid", q(uid)],
            ["property", q("Sheetname"), q(name), ["at", f(x), f(y - 0.7116), "0"],
             ["effects", ["font", ["size", "1.524", "1.524"], ["bold", "yes"]], ["justify", "left", "bottom"]]],
            ["property", q("Sheetfile"), q(file), ["at", f(x), f(y + h + 0.5846), "0"],
             ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "top"]]],
            ["instances", ["project", q(PROJECT), ["path", q("/" + ROOT_UUID), ["page", q(page)]]]]]


def text(s, x, y, size=1.27, bold=False):
    font = ["font", ["size", f(size), f(size)]] + ([["bold", "yes"]] if bold else [])
    return ["text", q(s), ["exclude_from_sim", "no"], ["at", f(x), f(y), "0"],
            ["effects", font, ["justify", "left", "bottom"]], ["uuid", q(ksch.uid())]]


def root_page() -> str:
    W, H = 100.33, 40.64
    boxes = [("ANALOG", "sheets/analog.kicad_sch", ANALOG_SHEET, 27.94, 55.88, "2",
              "Partners' front end: 4x INA333 (gain 501), DRL (MCP6002), vref, ADS131M08"),
             ("POWER", "sheets/power.kicad_sch", SHEET_UUID["power"], 157.48, 55.88, "3",
              "1S LiPo, power switch, TPS7A2033 low-noise +3.3V for the analog side"),
             ("MCU", "sheets/mcu.kicad_sch", SHEET_UUID["mcu"], 27.94, 111.76, "4",
              "Seeed XIAO nRF52840: SPI to the ADC, ADC clock, charge link"),
             ("PHOTODIODE", "sheets/photodiode.kicad_sch", SHEET_UUID["photodiode"], 157.48, 111.76, "5",
              "Screen-sync photodiode into ADC channel 4")]
    items = [text("SSVEP EEG board", 27.94, 33.02, size=3.048, bold=True),
             text("The sheets join by name: +3.3V and GND power symbols, and global labels\n"
                  "ADC_SCLK  ADC_DIN  ADC_DOUT  ADC_CS_N  ADC_DRDY_N  ADC_SYNC_RST  ADC_CLKIN\n"
                  "PD_OUT  VBAT  ANA_EN", 27.94, 40.64)]
    for name, file, uid, x, y, page, note in boxes:
        items.append(sheet_box(name, file, uid, x, y, W, H, page))
        items.append(text(note, x + 2.54, y + 6.35))
    doc = ["kicad_sch", ["version", ksch.VERSION], ["generator", q("eeschema")],
           ["generator_version", q("10.0")], ["uuid", q(ROOT_UUID)], ["paper", q("A4")],
           ["title_block", ["title", q("SSVEP EEG board")], ["date", q("2026-10-19")], ["rev", q("A")],
            ["company", q("SSVEP EEG board")],
            ["comment", "1", q("Root page: sheet boxes only")]],
           ["lib_symbols"]] + items + [["sheet_instances", ["path", q("/"), ["page", q("1")]]],
                                       ["embedded_fonts", "no"]]
    return ksch.dump(doc) + "\n"


def repath_pcb(raw: bytes) -> bytes:
    t = raw.decode("utf-8")
    t, n = re.subn(r'\(path "/([0-9a-f-]{36})"\)(\s+)\(sheetname "/"\)(\s+)\(sheetfile "SSVEP_PCB\.kicad_sch"\)',
                   lambda m: (f'(path "/{ANALOG_SHEET}/{m.group(1)}"){m.group(2)}(sheetname "/ANALOG/")'
                              f'{m.group(3)}(sheetfile "sheets/analog.kicad_sch")'), t)
    print(f"  PCB: {n} footprints re-pathed under /ANALOG/")
    return t.encode("utf-8")


def main():
    if sys.argv[1:] == ["--root-only"]:          # re-draw the root page; nothing else changes
        ROOT.write_bytes(root_page().encode("utf-8"))
        print(f"rewrote {ROOT.name}")
        return
    root_text = ROOT.read_bytes().decode("utf-8")
    if "sheets/analog.kicad_sch" in root_text:
        sys.exit("already restructured")
    BACKUP.mkdir(parents=True, exist_ok=True)
    for p in (ROOT, PCB):
        if not (BACKUP / p.name).exists():
            shutil.copy2(p, BACKUP / p.name)
    ANALOG.write_bytes(analog_page(root_text).encode("utf-8"))
    ROOT.write_bytes(root_page().encode("utf-8"))
    PCB.write_bytes(repath_pcb(PCB.read_bytes()))
    print(f"wrote {ROOT.name} (root), {ANALOG.relative_to(PROJ)}; backups in {BACKUP}")


if __name__ == "__main__":
    main()
