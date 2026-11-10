"""fix_partner_links.py -- link the partners' symbols to the footprints their layout already uses.

    python fix_partner_links.py

* Footprint fields: each symbol on sheets/analog.kicad_sch gets the footprint its PCB footprint
  actually is (matched by designator). The layout is the truth: U5's symbol said PBS0032A_N but
  the board uses Package_QFP:TQFP-32_5x5mm_P0.5mm.
* C28/C29/C30: the 100 nF REF bypass caps on U2/U3/U4 were placed one stub short of the REF pin
  (C27 on U1 is wired). One short wire each, on the partners' own layout grid.
* Library tables: the partners' downloaded libraries (ul_* folders) added to sym-lib-table and
  fp-lib-table under the nicknames their symbols and footprints already use.
Bytes in, bytes out; backup to design/backup/pre_links/ first.
"""
import re
import shutil
from pathlib import Path

import ksch
from ksch import f, q

PROJ = Path("C:/Users/aidan/SSVEP_PCB/SSVEP_PCB")
SHEET, PCB = PROJ / "sheets" / "analog.kicad_sch", PROJ / "SSVEP_PCB.kicad_pcb"
BACKUP = Path("C:/Users/aidan/SSVEP_PCB/design/backup/pre_links")
C_WIRES = [((101.6, 95.25), (104.14, 95.25)),      # U2 REF -> C28.1
           ((100.33, 139.7), (101.6, 139.7)),      # U3 REF -> C29.1
           ((100.33, 186.69), (102.87, 186.69))]   # U4 REF -> C30.1
UL = "${KIPRJMOD}/../"
SYM_LIBS = {"2026-10-18_07-15-18": "ul_INA333AIDGKR/KiCADv6/2026-10-18_07-15-18.kicad_sym",
            "2026-10-18_20-53-16": "ul_ADS131M08IPBS/KiCADv6/2026-10-18_20-53-16.kicad_sym",
            "2026-10-18_21-21-43": "ul_MCP6002-I-SN/KiCADv6/2026-10-18_21-21-43.kicad_sym"}
FP_LIBS = {"footprints": "ul_INA333AIDGKR/KiCADv6/footprints.pretty",
           "footprints_4": "ul_MCP6002-I-SN/KiCADv6/footprints.pretty"}


def pcb_footprints() -> dict:
    pcb = PCB.read_bytes().decode("utf-8")
    return {ref: name for name, ref in
            re.findall(r'\(footprint "([^"]*)".*?\(property "Reference" "([^"]+)"', pcb, re.S)}


def set_footprints(lines, fps):
    """Top-level `\\t(symbol` blocks: replace the instance's Footprint value."""
    changed, i = [], 0
    while i < len(lines):
        if lines[i].rstrip("\r\n") == "\t(symbol":
            j = i
            while lines[j].rstrip("\r\n") != "\t)":
                j += 1
            block = "".join(lines[i:j + 1])
            m = re.search(r'\(property "Reference" "([^"]+)"', block)
            ref = m.group(1) if m else ""
            if ref in fps:
                for k in range(i, j + 1):
                    mm = re.match(r'(\t\t\(property "Footprint" )"([^"]*)"(.*)', lines[k], re.S)
                    if mm:
                        if mm.group(2) != fps[ref]:
                            changed.append((ref, mm.group(2), fps[ref]))
                            lines[k] = f'{mm.group(1)}"{fps[ref]}"{mm.group(3)}'
                        break
            i = j + 1
        else:
            i += 1
    return changed


def add_table_entries(path: Path, head: str, libs: dict):
    text = path.read_text(encoding="utf-8")
    add = "".join(f'\t(lib (name "{n}")(type "KiCad")(uri "{UL}{p}")(options "")(descr "partners\' downloaded library"))\n'
                  for n, p in libs.items() if f'(name "{n}")' not in text)
    if add:
        text = text.rstrip().rstrip(")") + add + ")\n"
        path.write_text(text, encoding="utf-8", newline="\n")


def main():
    BACKUP.mkdir(parents=True, exist_ok=True)
    for p in (SHEET, PROJ / "sym-lib-table", PROJ / "fp-lib-table"):
        if not (BACKUP / p.name).exists():
            shutil.copy2(p, BACKUP / p.name)
    raw = SHEET.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.splitlines(keepends=True)
    changed = set_footprints(lines, pcb_footprints())
    text = "".join(lines)
    wires = [w for w in C_WIRES if f"(xy {f(w[0][0])} {f(w[0][1])}) (xy {f(w[1][0])} {f(w[1][1])})" not in text]
    block = "".join("\t" + ksch.dump(["wire", ["pts", ["xy", f(a[0]), f(a[1])], ["xy", f(b[0]), f(b[1])]],
                                       ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(ksch.uid())]], 1)
                    .replace("\n", nl) + nl for a, b in wires)
    at = text.rindex("\n\t(embedded_fonts") + 1          # the top-level one, not a lib symbol's
    SHEET.write_bytes((text[:at] + block + text[at:]).encode("utf-8"))
    add_table_entries(PROJ / "sym-lib-table", "sym_lib_table", SYM_LIBS)
    add_table_entries(PROJ / "fp-lib-table", "fp_lib_table", FP_LIBS)
    print(f"footprint fields set on {len(changed)} symbols; {len(wires)} REF-cap wires added")
    for ref, old, new in sorted(changed):
        if not new.startswith(("Capacitor_SMD", "Resistor_SMD")):
            print(f"  {ref}: {old!r} -> {new}")


if __name__ == "__main__":
    main()
