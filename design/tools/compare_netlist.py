"""compare_netlist.py -- does the drawn KiCad project implement the checked circuit JSON?

    python compare_netlist.py <kicad netlist.xml>

The truth is design/ssvep_board.circuit.json (ERC-clean); the drawing is whatever kicad-cli
exports from the partners' root sheet with our three sheets under it. Every net is compared as a
set of (designator, pad) pairs, with JSON refs mapped to the drawn designators below.
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path("C:/Users/aidan/schematica")
DESIGN = Path("C:/Users/aidan/SSVEP_PCB/design")
sys.path[:0] = [str(REPO / "eda" / "routing")]
import graph            # noqa: E402
import part_records     # noqa: E402

REFS = {  # flattened JSON ref -> drawn designator
    "MCU:U1": "U201", "MCU:R1": "R201", "MCU:R2": "R202", "MCU:R3": "R203", "MCU:R4": "R204",
    "MCU:R5": "R205", "MCU:R6": "R206", "MCU:R7": "R207", "MCU:Y1": "Y201", "MCU:C1": "C201",
    "MCU:R8": "R208", "MCU:C2": "C202", "MCU:TP1": "TP101", "MCU:J1": "J101", "MCU:SW1": "SW101",
    "MCU:U2": "U101", "MCU:C4": "C101", "MCU:C5": "C102", "MCU:TP2": "TP102", "MCU:TP3": "TP103",
    "MCU:F1": "F101", "MCU:Q1": "Q101", "MCU:R9": "R101", "MCU:R10": "R102",
    "PD:J1": "J301", "PD:R1": "R301", "PD:C1": "C301", "PD:R2": "R302", "PD:R3": "R303", "PD:C2": "C302",
}


def expected():
    with part_records.also_search(DESIGN / "parts"):
        g = graph.load(DESIGN / "ssvep_board.circuit.json")
    nets = {}
    for net in g.nets():
        pads = set()
        for pin in g.pins_on(net["name"]):
            ref = REFS.get(pin["ref"], pin["ref"].split(":", 1)[-1])
            pads |= {(ref, str(n)) for n in pin["numbers"]}
        nets[net["name"]] = frozenset(pads)
    return nets


def drawn(xml_path):
    root = ET.parse(xml_path).getroot()
    return {n.get("name"): frozenset((x.get("ref"), x.get("pin")) for x in n.findall("node")
                                     if not x.get("ref").startswith("#"))
            for n in root.find("nets")}


def main(xml_path):
    exp, got = expected(), drawn(xml_path)
    # a pad's net in each view
    where_e = {p: name for name, pads in exp.items() for p in pads}
    where_g = {p: name for name, pads in got.items() for p in pads}
    bad = 0
    exp_sets = {pads for pads in exp.values() if len(pads) > 1}
    got_sets = {pads for pads in got.values() if len(pads) > 1}
    for pads in sorted(exp_sets - got_sets, key=lambda s: sorted(s)):
        bad += 1
        name = where_e[next(iter(pads))]
        split = {}
        for p in pads:
            split.setdefault(where_g.get(p, "<missing>"), []).append(p)
        print(f"MISMATCH {name}: expected {len(pads)} pads; drawn as " +
              " | ".join(f"{k}: {sorted(v)}" for k, v in split.items()))
    for pads in sorted(got_sets - exp_sets, key=lambda s: sorted(s)):
        if not any(pads <= e for e in exp_sets):
            name = where_g[next(iter(pads))]
            print(f"EXTRA drawn net {name}: {sorted(pads)}")
            bad += 1
    print(f"{len(exp_sets)} multi-pin nets expected, {len(got_sets)} drawn, {bad} differences")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
