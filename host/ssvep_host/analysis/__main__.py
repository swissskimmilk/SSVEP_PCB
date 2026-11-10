"""python -m ssvep_host.analysis SESSION_FOLDER [--method cca|fbcca] [--length S]"""

import argparse
from pathlib import Path

import numpy as np

from . import analyse


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--method", default="fbcca", choices=["cca", "fbcca"])
    ap.add_argument("--length", type=float, default=None, help="epoch length in seconds")
    ap.add_argument("--delay", type=float, default=0.14, help="visual latency to skip, s")
    a = ap.parse_args()

    r = analyse(a.folder, a.method, a.length, a.delay)
    print(f"fs {r['fs']:.2f} Hz, display {r['refresh'] or float('nan'):.2f} Hz, targets {r['freqs']}")
    print(f"{'trial':>5} {'target':>6} {'freq':>6} {'pd_freq':>7} {'drops':>5} {'lag_ms':>7} {'pred':>5}")
    for t, p in zip(r["trials"], list(r["pred"]) + [None] * len(r["trials"])):
        print(f"{t.trial:>5} {t.target:>6} {t.freq:>6.2f} {t.measured_freq:>7.2f} {t.drops:>5} "
              f"{t.host_offset_ms:>7.1f} {'' if p is None else p:>5}")
    for n in r["notes"]:
        print("note:", n)
    if len(r["y"]):
        print(f"{a.method} accuracy: {r['accuracy'] * 100:.1f}% ({int(np.sum(r['pred'] == r['y']))}/{len(r['y'])})")


if __name__ == "__main__":
    main()
