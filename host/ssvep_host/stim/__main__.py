"""Run the stimulus on its own, without the board: python -m ssvep_host.stim [--windowed]

Useful for checking a monitor: it prints the refresh rate and missed vsyncs per trial.
"""

import argparse
import multiprocessing as mp
import queue

from .config import StimConfig, grid_targets
from .window import run_stimulus


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--freqs", default="12,15", help="comma-separated Hz (default: 2 targets)")
    ap.add_argument("--trials", type=int, default=2, help="trials per target")
    ap.add_argument("--screen", type=int, default=0)
    ap.add_argument("--windowed", action="store_true")
    ap.add_argument("--waveform", default="square", choices=["square", "sine"])
    ap.add_argument("--layout", default="corners", choices=["corners", "grid"])
    ap.add_argument("--calibrate", action="store_true", help="photodiode patch white/black only")
    a = ap.parse_args()

    cfg = StimConfig(targets=grid_targets([float(f) for f in a.freqs.split(",")]),
                     trials_per_target=a.trials, screen=a.screen, windowed=a.windowed,
                     waveform=a.waveform, layout=a.layout)
    ctx = mp.get_context("spawn")
    events, abort = ctx.Queue(), ctx.Event()
    p = ctx.Process(target=run_stimulus,
                    args=("calibrate" if a.calibrate else "session", cfg.to_dict(), events, abort))
    p.start()
    while p.is_alive() or not events.empty():
        try:
            ev = events.get(timeout=0.5)
        except queue.Empty:
            continue
        if ev["kind"] == "refresh":
            print(f"display {ev['hz']:.3f} Hz (measured {ev['measured_hz']:.2f}), "
                  f"{ev.get('waveform', '')}, order {ev['order']}")
            if ev.get("uneven"):
                print(f"  uneven square-wave frequencies at this refresh: {ev['uneven']}")
        elif ev["kind"] == "stim_start":
            print(f"trial {ev['trial']}: {ev['freq']:g} Hz")
        elif ev["kind"] == "rest_start" and ev["trial"] >= 0:
            print(f"  missed vsyncs during stimulus: {ev['drops_in_stim']}")
        elif ev["kind"] in ("done", "aborted"):
            print(f"{ev['kind']}: {ev['drops']} of {ev['frame']} vsyncs missed")


if __name__ == "__main__":
    main()
