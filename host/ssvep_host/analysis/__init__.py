"""Offline analysis of recorded sessions."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import recorder
from .cca import classify
from .epochs import contiguous, epochs, match_trials


def analyse(folder: Path, method: str = "fbcca", length_s: float | None = None,
            delay_s: float = 0.14) -> dict:
    arrays, log = recorder.load(folder)
    rec = contiguous(arrays)
    events = log["events"]
    refresh = next((e for e in events if e["kind"] == "refresh"), {})
    targets = refresh.get("targets", [])
    freqs = [t["freq"] for t in targets]
    stim_s = log["meta"].get("stim", {}).get("stim_s", 4.0)
    length_s = length_s or max(0.5, stim_s - delay_s)

    levels = log["meta"].get("pd_levels")
    trials, notes = match_trials(rec, events, levels=tuple(levels) if levels else None)
    X, y = epochs(rec, trials, length_s, delay_s)
    pred = classify(X, freqs, rec.fs, method) if len(X) else np.array([], int)
    return dict(fs=rec.fs, freqs=freqs, trials=trials, notes=notes, y=y, pred=pred,
                accuracy=float(np.mean(pred == y)) if len(y) else float("nan"),
                refresh=refresh.get("hz"))
