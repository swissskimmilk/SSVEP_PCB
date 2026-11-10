"""gen_symbols.py -- house-style symbols for our parts, generated from their part records.

    python gen_symbols.py      # -> SSVEP_PCB/libs/SSVEP.kicad_sym

Each symbol comes from eda/routing/parts/symbol_from_part.build(record), the same generator the
schematic engine uses: the record says what each pin IS, the generator decides where it goes.
Passives and rails stay on KiCad's Device:/power: symbols to match the partners' sheet.
Generic parts with a glyph (MOSFET, fuse) are copied from the house autosch library,
which numbers their pins the way the generic part records do (KiCad 10's Device:Q_PMOS numbers
pins D/G/S, which no SOT-23 footprint matches).
"""
import json
import sys
from pathlib import Path

ROUTING = Path("C:/Users/aidan/schematica/eda/routing")
sys.path[:0] = [str(ROUTING), str(ROUTING / "parts")]
import symbol_from_part  # noqa: E402

PARTS = Path("C:/Users/aidan/SSVEP_PCB/design/parts")
OUT = Path("C:/Users/aidan/SSVEP_PCB/libs/SSVEP.kicad_sym")
RECORDS = ["xiao-nrf52840", "lp5907mfx-3.3", "ecs-2520mvlc-081.92-cn-tr", "eg1218",
           "b2b-ph-k-s", "5015"]
AUTOSCH = Path("C:/Users/aidan/schematica/app/backend/libraries/autosch.kicad_sym")
GLYPHS = ["Q_PMOS", "Fuse"]


def glyph_block(text: str, name: str) -> str:
    """One top-level `(symbol "name" ...)` out of autosch.kicad_sym, by paren depth."""
    start = text.index(f'\n  (symbol "{name}"') + 3
    depth = 0
    for i in range(start, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return text[start:i + 1]
    raise ValueError(f"unterminated symbol {name}")


def symbol_block(text: str) -> str:
    """The `(symbol ...)` inside a one-symbol `(kicad_symbol_lib ...)`."""
    start = text.index("(symbol ")
    end = text.rstrip().rindex(")")          # the library's own closing paren
    return text[start:end].rstrip()


def main():
    blocks, report = [], []
    for name in RECORDS:
        part = json.loads((PARTS / f"{name}.part.json").read_text(encoding="utf-8"))
        text, w, h = symbol_from_part.build(part)
        blocks.append("  " + symbol_block(text))
        report.append(f"  {part['part_number']:<28} {w:6.2f} x {h:6.2f} mm")
    autosch = AUTOSCH.read_text(encoding="utf-8")
    for name in GLYPHS:
        blocks.append(glyph_block(autosch, name))
        report.append(f"  {name:<28} (autosch glyph)")
    OUT.write_text("(kicad_symbol_lib (version 20211014) (generator autosch)\n"
                   + "\n".join(blocks) + "\n)\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT}\n" + "\n".join(report))


if __name__ == "__main__":
    main()
