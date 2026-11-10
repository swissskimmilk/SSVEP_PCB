"""fix_adc_pins.py -- two ADS131M08 (U5) supply-pin fixes on the partners' page.

    python fix_adc_pins.py

* Pin 27 is NC on the PBS package (datasheet Table 5-1: "Leave unconnected or connect to AGND").
  The Ultra Librarian symbol calls it a second AVDD, and patch_partner.py wired it to +3.3V on
  that word. The wire comes off, the pin gets a no-connect flag, and the symbol's pin 27 becomes
  NC / no_connect in both the sheet's cached copy and the ul_ADS131M08IPBS library. The +3.3V
  symbol that sat on pin 15 (its glyph covered pin 27's end) moves 12.7 mm left onto the C40 wire.
* DVDD (pin 26, the symbol's IOVDD) had no capacitor of its own; the datasheet asks for 1 uF to
  DGND on DVDD as well as on AVDD. C43 1 uF goes straight across pins 26 and 25.
Bytes in, bytes out; backup to design/backup/pre_adc_fix/ first.
"""
import re
import shutil
import uuid
from pathlib import Path

PROJ = Path("C:/Users/aidan/SSVEP_PCB")
SHEET = PROJ / "SSVEP_PCB" / "sheets" / "analog.kicad_sch"
UL_LIB = PROJ / "ul_ADS131M08IPBS" / "KiCADv6" / "2026-10-18_20-53-16.kicad_sym"
BACKUP = PROJ / "design" / "backup" / "pre_adc_fix"
PWR_X = "200.66"                        # new home of the +3.3V symbol, on the C40 -> pin 15 wire


def blocks(text, nl):
    """Top-level items as (start, end) line spans; a span is `\\t(kind` .. `\\t)`."""
    lines = text.split(nl)
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith("\t(") and not lines[i].startswith("\t(" + " "):
            j = i
            if not lines[i].rstrip().endswith(")") or lines[i].count("(") != lines[i].count(")"):
                while lines[j] != "\t)":
                    j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return lines, out


def wire(a, b, nl):
    return nl.join(["\t(wire", "\t\t(pts", f"\t\t\t(xy {a[0]} {a[1]}) (xy {b[0]} {b[1]})", "\t\t)",
                    "\t\t(stroke", "\t\t\t(width 0)", "\t\t\t(type default)", "\t\t)",
                    f'\t\t(uuid "{uuid.uuid4()}")', "\t)"])


def no_connect(p, nl):
    return nl.join(["\t(no_connect", f"\t\t(at {p[0]} {p[1]})", f'\t\t(uuid "{uuid.uuid4()}")', "\t)"])


def pin27_to_nc(text):
    """The pin block numbered 27: power_in -> no_connect, name AVDD -> NC. Exactly one per file.
    Every gap is whitespace only, so the match cannot run from one pin block into the next."""
    pat = re.compile(r'\(pin power_in (line\s*\(at [-\d. ]+\)\s*\(length [\d.]+\)\s*\(name )"AVDD"'
                     r'(\s*\(effects\s*\(font\s*\(size [\d. ]+\)\s*\)\s*\)\s*\)\s*\(number "27")')
    new, n = pat.subn(r'(pin no_connect \1"NC"\2', text)
    assert n == 1, f"pin 27 block matched {n} times"
    return new


def c43_from_c41(block, nl):
    """C41's symbol block re-made as C43 at (269.24, 99.06), upright, fields to its right."""
    b = re.sub(r'"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"',
               lambda m: f'"{uuid.uuid4()}"', block)
    b = b.replace('"C41"', '"C43"').replace("(fields_autoplaced yes)", "(fields_autoplaced no)")
    b = b.replace("(at 190.5 99.06 270)", "(at 269.24 99.06 0)")
    b = b.replace("(at 190.5 91.44 90)", "(at 271.78 97.79 0)")
    b = b.replace("(at 190.5 93.98 90)", "(at 271.78 100.33 0)")
    b = b.replace("(at 186.69 100.0252 0)", "(at 269.24 99.06 0)")
    b = b.replace("(at 190.5 99.06 0)", "(at 269.24 99.06 0)")
    assert "190.5" not in b and "186.69" not in b, "C41 layout changed -- check c43_from_c41"
    # Reference and Value read left-to-right from their anchor
    for name in ("Reference", "Value"):
        b = re.sub(r'(\(property "%s" [\s\S]*?\(effects\s*\(font\s*\(size 1\.27 1\.27\)\s*\))' % name,
                   lambda m: m.group(1) + nl + "\t\t\t\t(justify left)", b, count=1)
    return b


def main():
    BACKUP.mkdir(parents=True, exist_ok=True)
    for p in (SHEET, UL_LIB):
        if not (BACKUP / p.name).exists():
            shutil.copy2(p, BACKUP / p.name)
    raw = SHEET.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines, spans = blocks(raw, nl)
    drop, replace, c41 = set(), {}, None
    for i, j in spans:
        body = nl.join(lines[i:j + 1])
        head = lines[i]
        if head == "\t(wire" and "(xy 213.36 85.09)" in body and "(xy 213.36 87.63)" in body:
            drop.add((i, j))                                   # pin 27 -> pin 15 wire
        elif head == "\t(wire" and "(xy 194.31 87.63) (xy 213.36 87.63)" in body:
            replace[(i, j)] = nl.join([wire(("194.31", "87.63"), (PWR_X, "87.63"), nl),
                                       wire((PWR_X, "87.63"), ("213.36", "87.63"), nl)])
        elif head == "\t(junction" and "(at 213.36 87.63)" in body:
            drop.add((i, j))                                   # only pin 15 + one wire remain
        elif head == "\t(symbol" and '"#PWR033"' in body:
            assert '(lib_id "power:+3.3V")' in body and "(at 213.36 87.63 0)" in body
            replace[(i, j)] = body.replace("(at 213.36 ", f"(at {PWR_X} ")
        elif head == "\t(symbol" and '(property "Reference" "C41"' in body:
            c41 = body
    assert len(drop) == 2 and len(replace) == 2 and c41, (drop, list(replace), bool(c41))
    out, k = [], 0
    for i, j in spans:
        out.append(nl.join(lines[k:i]))
        if (i, j) in drop:
            pass
        elif (i, j) in replace:
            out.append(replace[(i, j)])
        else:
            out.append(nl.join(lines[i:j + 1]))
        k = j + 1
    out.append(nl.join(lines[k:]))
    text = nl.join(s for s in out if s != "")
    text = pin27_to_nc(text)
    add = [no_connect(("213.36", "85.09"), nl),
           c43_from_c41(c41, nl),
           wire(("264.16", "95.25"), ("269.24", "95.25"), nl),       # DVDD pin 26 -> C43.1
           wire(("264.16", "102.87"), ("269.24", "102.87"), nl)]     # DGND pin 25 -> C43.2
    at = text.rindex(nl + "\t(embedded_fonts") + len(nl)
    text = text[:at] + nl.join(add) + nl + text[at:]
    SHEET.write_bytes(text.encode("utf-8"))

    lib = UL_LIB.read_bytes().decode("utf-8")
    UL_LIB.write_bytes(pin27_to_nc(lib).encode("utf-8"))
    print("U5 pin 27 -> NC (wire removed, flag added, symbol fixed); +3.3V symbol moved to x 200.66;"
          " C43 1u added on DVDD")


if __name__ == "__main__":
    main()
