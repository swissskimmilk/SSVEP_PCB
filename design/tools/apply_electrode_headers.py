"""apply_electrode_headers.py -- part selection for the electrode connectors J1-J6 on the partners' page.

    python apply_electrode_headers.py

The partners' symbols (Connector:Conn_01x01_Pin) already sit on PinHeader_1x01_P2.54mm_Vertical
footprints, so nothing is redrawn or re-laid-out: each gets Datasheet plus hidden Manufacturer,
MPN and DigiKey_PN fields. Samtec TSW-101-07-G-S: one 0.025" square post on 0.100", gold
plated (the leads' gold-socket contacts mate gold-to-gold). Bytes in, bytes out; backup to
design/backup/pre_headers/ first.
"""
import re
import shutil
from pathlib import Path

import ksch
from ksch import f, q

SHEET = Path("C:/Users/aidan/SSVEP_PCB/SSVEP_PCB/sheets/analog.kicad_sch")
BACKUP = Path("C:/Users/aidan/SSVEP_PCB/design/backup/pre_headers")
REFS = ("J1", "J2", "J3", "J4", "J5", "J6")
FOOTPRINT = "Connector_PinHeader_2.54mm:PinHeader_1x01_P2.54mm_Vertical"
DATASHEET = "https://suddendocs.samtec.com/catalog_english/tsw_th.pdf"
FIELDS = (("Manufacturer", "Samtec"), ("MPN", "TSW-101-07-G-S"), ("DigiKey_PN", "612-TSW-101-07-G-S-ND"))


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
    out, i, done = [], 0, []
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
        if ref in REFS:
            if '(property "MPN"' in text:
                raise SystemExit(f"{ref} already has an MPN -- already applied?")
            if f'(property "Footprint" "{FOOTPRINT}"' not in text:
                raise SystemExit(f"{ref}: footprint is not {FOOTPRINT} -- sheet changed?")
            at = re.search(r'^\t\t\(at ([-\d.]+) ([-\d.]+)', text, re.M)
            x, y = float(at.group(1)), float(at.group(2))
            new, inserted = [], False
            for line in block:
                md = re.match(r'(\t\t\(property "Datasheet" )"([^"]*)"(.*)', line, re.S)
                if md:
                    line = f'{md.group(1)}"{DATASHEET}"{md.group(3)}'
                elif not inserted and line.startswith("\t\t(pin "):
                    new += [prop_line(k, v, x, y, nl) for k, v in FIELDS]
                    inserted = True
                new.append(line)
            block = new
            done.append(ref)
        out += block
        i = j + 1
    missing = sorted(set(REFS) - set(done))
    if missing:
        raise SystemExit(f"not found on the sheet: {missing}")
    SHEET.write_bytes("".join(out).encode("utf-8"))
    print(f"part fields added to {', '.join(sorted(done))}: Samtec TSW-101-07-G-S")


if __name__ == "__main__":
    main()
