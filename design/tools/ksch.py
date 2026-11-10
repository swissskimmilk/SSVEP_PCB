"""ksch.py -- write KiCad 10 schematic sheets by hand, with real library symbols.

Placement and wiring are explicit: a sheet script places each symbol at a chosen point, asks
`pin(ref, name)` where a pin's connection point landed, and draws wires, labels and power
symbols there. Library symbols are copied (flattened) into the sheet's lib_symbols cache, so the
file opens without any library table.
"""
from __future__ import annotations

import math
import re
import uuid as _uuid
from pathlib import Path

KICAD_SYM = Path("C:/Program Files/KiCad/10.0/share/kicad/symbols")
PROJECT_LIBS = {"Seeed_Studio_XIAO_Series": Path("C:/Users/aidan/SSVEP_PCB/libs/Seeed_Studio_XIAO_Series.kicad_sym"),
                "SSVEP": Path("C:/Users/aidan/SSVEP_PCB/libs/SSVEP.kicad_sym")}      # gen_symbols.py
VERSION = "20260306"
GRID = 1.27


# ---------------------------------------------------------------- s-expressions
def parse(text: str):
    tokens = re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+', text)
    stack, cur = [], []
    for t in tokens:
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            done, cur = cur, stack.pop()
            cur.append(done)
        else:
            cur.append(t)
    return cur[0]


def dump(node, depth=0) -> str:
    if not isinstance(node, list):
        return node
    if all(not isinstance(x, list) for x in node):
        return "(" + " ".join(node) + ")"
    pad = "\t" * (depth + 1)
    head = [x for x in node if not isinstance(x, list)]
    out = "(" + " ".join(head)
    for x in node:
        if isinstance(x, list):
            out += "\n" + pad + dump(x, depth + 1)
    return out + "\n" + "\t" * depth + ")"


def q(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def unq(s: str) -> str:
    return s[1:-1].replace('\\"', '"').replace("\\\\", "\\") if s.startswith('"') else s


def child(node, key):
    return next((x for x in node if isinstance(x, list) and x and x[0] == key), None)


def uid() -> str:
    return str(_uuid.uuid4())


def f(v: float) -> str:
    v = round(v, 4)
    return str(int(v)) if v == int(v) else repr(v)


# ---------------------------------------------------------------- library symbols
_LIB_CACHE: dict = {}


def _lib(libname: str):
    if libname not in _LIB_CACHE:
        path = PROJECT_LIBS.get(libname) or KICAD_SYM / f"{libname}.kicad_sym"
        _LIB_CACHE[libname] = parse(path.read_text(encoding="utf-8"))
    return _LIB_CACHE[libname]


def _find(libname: str, name: str):
    for x in _lib(libname):
        if isinstance(x, list) and x[:1] == ["symbol"] and unq(x[1]) == name:
            return x
    raise KeyError(f"{libname}:{name} not found")


def lib_symbol(lib_id: str):
    """The symbol as it goes into a sheet's lib_symbols: named lib_id, `extends` flattened."""
    libname, name = lib_id.split(":", 1)
    sym = _find(libname, name)
    ext = child(sym, "extends")
    if ext:
        parent = _find(libname, unq(ext[1]))
        own_props = {unq(p[1]): p for p in sym if isinstance(p, list) and p[0] == "property"}
        body = []
        for x in parent:
            if isinstance(x, list) and x[0] == "property" and unq(x[1]) in own_props:
                body.append(own_props.pop(unq(x[1])))
            elif isinstance(x, list) and x[0] == "symbol":          # units: rename parent -> child
                body.append([x[0], q(unq(x[1]).replace(unq(parent[1]), name, 1))] + x[2:])
            else:
                body.append(x)
        body += list(own_props.values())
        sym = body
    out = ["symbol", q(lib_id)] + [x for x in sym[2:] if not (isinstance(x, list) and x[0] == "extends")]
    return _modern(out)


def _modern(node):
    """Older library files write a bare `hide` token; a KiCad 10 sheet wants `(hide yes)`."""
    if not isinstance(node, list):
        return node
    bare = "hide" in node[1:]                      # `(effects ... hide)`, never `(hide yes)` itself
    out = node[:1] + [_modern(x) for x in node[1:] if x != "hide"]
    if bare:
        out.append(["hide", "yes"])
    return out


def pins_of(lib_id: str) -> dict:
    """{pin number: (name, x, y, etype)} in symbol coordinates (y up), connection points."""
    out = {}
    for unit in lib_symbol(lib_id):
        if isinstance(unit, list) and unit[0] == "symbol":
            for p in unit:
                if isinstance(p, list) and p[0] == "pin":
                    at = child(p, "at")
                    out[unq(child(child(p, "number"), "number")[1]) if False else unq(child(p, "number")[1])] = (
                        unq(child(p, "name")[1]), float(at[1]), float(at[2]), p[1])
    return out


# ---------------------------------------------------------------- the sheet
class Sheet:
    def __init__(self, title: str, project: str, root_uuid: str, sheet_uuid: str, paper: str = "A4",
                 page: str = "1", date: str = "", rev: str = "", company: str = "", comments=()):
        self.title, self.project, self.paper = title, project, paper
        self.path = f"/{root_uuid}/{sheet_uuid}"
        self.uuid = uid()
        self.page, self.date, self.rev, self.company, self.comments = page, date, rev, company, comments
        self.libs: dict = {}
        self.items: list = []
        self.parts: dict = {}             # ref -> (lib_id, x, y, rot, mirror)
        self.pwr_n = 0

    # -- symbols
    def place(self, ref, lib_id, x, y, rot=0, value=None, footprint="", datasheet="", mpn="",
              fields=None, dnp=False, ref_at=None, val_at=None, hide_value=False, extra=None, field_angle=0,
              mirror=None, on_board=True, in_bom=True):
        if lib_id not in self.libs:
            self.libs[lib_id] = lib_symbol(lib_id)
        pins = pins_of(lib_id)
        self.parts[ref] = (lib_id, x, y, rot, mirror)
        rx, ry = ref_at if ref_at else (x + 2.54, y - 2.54)
        vx, vy = val_at if val_at else (x + 2.54, y + 2.54)
        props = [
            self._prop("Reference", ref, rx, ry, justify="left", angle=field_angle),
            self._prop("Value", value or lib_id.split(":")[1], vx, vy, justify="left", hide=hide_value,
                       angle=field_angle),
            self._prop("Footprint", footprint, x, y, hide=True),
            self._prop("Datasheet", datasheet, x, y, hide=True),
        ]
        if mpn:
            props.append(self._prop("MPN", mpn, x, y, hide=True))
        for k, v in (fields or {}).items():
            props.append(self._prop(k, v, x, y, hide=True))
        node = ["symbol", ["lib_id", q(lib_id)], ["at", f(x), f(y), f(rot)]]
        if mirror:
            assert rot == 0, "mirror is only supported at rotation 0"
            node.append(["mirror", mirror])
        node += [["unit", "1"],
                ["exclude_from_sim", "no"], ["in_bom", "yes" if in_bom and not ref.startswith("#") else "no"],
                ["on_board", "yes" if on_board and not ref.startswith("#") else "no"],
                ["dnp", "yes" if dnp else "no"], ["fields_autoplaced", "no"], ["uuid", q(uid())]]
        node += props
        node += [["pin", q(n), ["uuid", q(uid())]] for n in pins]
        node.append(["instances", ["project", q(self.project),
                                   ["path", q(self.path), ["reference", q(ref)], ["unit", "1"]]]])
        self.items.append(node)
        return ref

    def _prop(self, name, value, x, y, justify=None, hide=False, size=1.27, angle=0):
        eff = ["effects", ["font", ["size", f(size), f(size)]]]
        if justify:
            eff.append(["justify", justify])
        if hide:
            eff.append(["hide", "yes"])
        return ["property", q(name), q(value), ["at", f(x), f(y), str(angle)], eff]

    def pin(self, ref, key):
        """Sheet coordinates of a pin's connection point; key = pin number or unique name."""
        lib_id, x, y, rot, mirror = self.parts[ref]
        pins = pins_of(lib_id)
        if key in pins:
            _, px, py, _ = pins[key]
        else:
            hits = [v for v in pins.values() if v[0] == key]
            if len(hits) != 1:
                raise KeyError(f"{ref}: pin {key!r} -> {len(hits)} matches; pins {sorted(pins)}")
            _, px, py, _ = hits[0]
        if mirror == "y":
            px = -px
        elif mirror == "x":
            py = -py
        a = math.radians(rot)
        sx = px * math.cos(a) - py * math.sin(a)
        sy = px * math.sin(a) + py * math.cos(a)
        return (round(x + sx, 4), round(y - sy, 4))

    # -- connectivity
    def wire(self, *pts):
        pts = [p for p in pts]
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            self.items.append(["wire", ["pts", ["xy", f(a[0]), f(a[1])], ["xy", f(b[0]), f(b[1])]],
                               ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(uid())]])

    def junction(self, p):
        self.items.append(["junction", ["at", f(p[0]), f(p[1])], ["diameter", "0"],
                           ["color", "0", "0", "0", "0"], ["uuid", q(uid())]])

    def nc(self, p):
        self.items.append(["no_connect", ["at", f(p[0]), f(p[1])], ["uuid", q(uid())]])

    def label(self, name, p, angle=0):
        just = {0: ["justify", "left", "bottom"], 180: ["justify", "right", "bottom"],
                90: ["justify", "left", "bottom"], 270: ["justify", "right", "bottom"]}[angle]
        self.items.append(["label", q(name), ["at", f(p[0]), f(p[1]), str(angle)],
                           ["fields_autoplaced", "yes"],
                           ["effects", ["font", ["size", "1.27", "1.27"]], just], ["uuid", q(uid())]])

    def glabel(self, name, p, angle=0, shape="bidirectional"):
        """Global label; angle 0 = body extends right of p, 180 = left."""
        just = "left" if angle in (0, 90) else "right"
        self.items.append(["global_label", q(name), ["shape", shape], ["at", f(p[0]), f(p[1]), str(angle)],
                           ["fields_autoplaced", "yes"],
                           ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", just]],
                           ["uuid", q(uid())],
                           ["property", q("Intersheetrefs"), q("${INTERSHEET_REFS}"),
                            ["at", f(p[0]), f(p[1]), "0"],
                            ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", just], ["hide", "yes"]]]])

    def power(self, lib_id, p, rot=0):
        self.pwr_n += 1
        name = lib_id.split(":")[1]
        ref = f"#PWR{self.page}{self.pwr_n:02d}"
        flip = rot == 180
        self.place(ref, lib_id, p[0], p[1], rot=rot, value=name,
                   ref_at=(p[0], p[1] + (3.81 if not flip else -3.81)),
                   val_at=(p[0] - 1.5, p[1] + (-3.6 if name != "GND" else 3.8)))
        # power symbols: hide reference, keep value
        node = self.items[-1]
        for x in node:
            if isinstance(x, list) and x[0] == "property" and unq(x[1]) == "Reference":
                x[-1].append(["hide", "yes"])
        return ref

    def text(self, s, p, size=1.27, bold=False):
        font = ["font", ["size", f(size), f(size)]] + ([["bold", "yes"]] if bold else [])
        self.items.append(["text", q(s), ["exclude_from_sim", "no"], ["at", f(p[0]), f(p[1]), "0"],
                           ["effects", font, ["justify", "left", "bottom"]], ["uuid", q(uid())]])

    def box(self, x0, y0, x1, y1):
        self.items.append(["rectangle", ["start", f(x0), f(y0)], ["end", f(x1), f(y1)],
                           ["stroke", ["width", "0"], ["type", "dash"]], ["fill", ["type", "none"]],
                           ["uuid", q(uid())]])

    # -- output
    def write(self, path: Path):
        tb = ["title_block", ["title", q(self.title)]]
        if self.date:
            tb.append(["date", q(self.date)])
        if self.rev:
            tb.append(["rev", q(self.rev)])
        if self.company:
            tb.append(["company", q(self.company)])
        for i, c in enumerate(self.comments, 1):
            tb.append(["comment", str(i), q(c)])
        doc = ["kicad_sch", ["version", VERSION], ["generator", q("eeschema")],
               ["generator_version", q("10.0")], ["uuid", q(self.uuid)], ["paper", q(self.paper)], tb,
               ["lib_symbols"] + list(self.libs.values())]
        doc += self.items
        doc.append(["embedded_fonts", "no"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((dump(doc) + "\n").encode("utf-8"))      # LF, like eeschema writes
