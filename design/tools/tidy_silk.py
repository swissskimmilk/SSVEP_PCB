"""tidy_silk.py -- clear the board's silkscreen DRC warnings (2026-11-02).

    python tidy_silk.py

U201 (XIAO nRF52840): the footprint's module outline runs over its own castellated pads, and its
USB-C outline hangs past the board's right edge. The module marks its own place, so every silk
line and arc of U201 goes, with the circle that sits off the edge; the pin-1 dot by pad 1 and the
U201 reference stay. U6 (MCP6002): its pin-1 '*' is drawn twice on silk and on fab; the second of
each pair goes. Items are removed by uuid, text in, text out (KiCad's Python bindings lose their
footprint wrappers once an item is removed). Backup: design/backup/SSVEP_PCB.kicad_pcb.pre_silk_tidy.
"""
import re
from pathlib import Path

BOARD = Path("C:/Users/aidan/SSVEP_PCB/SSVEP_PCB/SSVEP_PCB.kicad_pcb")
GONE = {
    "U201": ["dd61666d-daa1-438b-8623-52b48dfeba4d", "471aa0fd-51c0-455c-b3b9-bc48f16dc1b3",
             "12b95781-b405-4a0f-98cf-ba73de13f465", "0d37d5fe-762a-4e9b-8b3e-c2993dae9c7d",
             "798ba6c4-678b-4d06-bb2e-3fc72e209a43", "05c87b46-b976-4959-a0ad-f75abac05c12",
             "cec92616-bfae-48f8-a862-beb0c02addb5", "91285c0a-2ef0-4d9e-a088-a3058600518d",
             "d305b18a-31f5-4f6f-8af3-7a1890063c5", "78397c6a-a99e-498c-8ee0-73af6f94747b",
             "13fa3a66-33c4-4787-9081-62336fdf", "d81268c5-3dc9-4ca8-8e", "9086f13d-dd7c-4c87-bd4b-6e0",
             "dc8dc49d-f252-4b05-9b6d-e31d1b196fd6"],                       # the off-edge circle
    "U6": ["a9d35aff-5c2c-40bd-b6ef-a19bd0134700", "eeaed5fd-11e6-4367-ac50-b66e738b5aca"],
}


def main():
    text = BOARD.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    removed = []
    for ref, uuids in GONE.items():
        i = text.index(f'(property "Reference" "{ref}"')
        start = text.rindex(f"{nl}\t(footprint", 0, i)
        end = text.index(f"{nl}\t)", i)
        block = text[start:end]
        for u in uuids:
            # one item: from its "\n\t\t(" opener to the next one at the same depth
            m = re.search(r"\n\t\t\((fp_\w+)(?:(?!\n\t\t\().)*?\(uuid \"" + re.escape(u) + r"[^\"]*\"",
                          block, re.S)
            if not m:
                raise SystemExit(f"{ref}: no item with uuid {u}")
            k = block.find(f"{nl}\t\t(", m.end())
            k = len(block) if k < 0 else k
            removed.append(f"{ref} {m.group(1)} {u[:8]}")
            block = block[:m.start() - (len(nl) - 1)] + block[k:]
        text = text[:start] + block + text[end:]
    BOARD.write_bytes(text.encode("utf-8"))
    print(f"{len(removed)} silk items removed:\n  " + "\n  ".join(removed))


if __name__ == "__main__":
    main()
