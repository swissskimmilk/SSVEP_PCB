"""Find stimulus onsets in the photodiode channel and cut EEG epochs at them.

The sync patch is black between trials, fully white for the first few frames of a
trial (the onset marker), then mirrors the cued target. An onset is the patch
crossing half-scale after at least `min_rest_s` of darkness.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .. import protocol as P


@dataclass
class Trial:
    trial: int
    target: int
    freq: float
    onset: float          # fractional sample index (into the contiguous record)
    measured_freq: float  # photodiode peak during the stimulus
    drops: int            # frames the stimulus window reported missing
    host_offset_ms: float # onset minus host-clock prediction: display + link latency


@dataclass
class Record:
    fs: float
    channels: list[int]
    data: np.ndarray      # (n, ch) contiguous by sample index, NaN where samples were lost
    first_index: int
    packet_index: np.ndarray
    packet_time: np.ndarray

    def channel(self, ch: int) -> np.ndarray:
        return self.data[:, self.channels.index(ch)]


def contiguous(arrays: dict) -> Record:
    index = arrays["index"].astype(np.int64)
    data = arrays["data"]
    first = int(index[0]) if len(index) else 0
    n = int(index[-1] - first + 1) if len(index) else 0
    full = np.full((n, data.shape[1]), np.nan)
    full[index - first] = data
    return Record(float(arrays["fs"]), [int(c) for c in arrays["channels"]], full, first,
                  arrays["packet_index"] - first, arrays["packet_time"])


def pd_levels(pd: np.ndarray) -> tuple[float, float]:
    finite = pd[np.isfinite(pd)]
    return float(np.percentile(finite, 2)), float(np.percentile(finite, 99.5))


def pd_onsets(pd: np.ndarray, fs: float, min_rest_s: float = 0.5,
              levels: tuple[float, float] | None = None) -> np.ndarray:
    lo, hi = levels or pd_levels(pd)
    x = np.nan_to_num(pd, nan=lo)
    thr = lo + 0.5 * (hi - lo)
    quiet = (x < lo + 0.15 * (hi - lo)).astype(np.int64)
    quiet_run = np.concatenate([[0], np.cumsum(quiet)])
    rest = int(min_rest_s * fs)
    above = x > thr
    out = []
    for i in np.flatnonzero(above[1:] & ~above[:-1]) + 1:
        if i - 1 - rest < 0:
            continue
        if quiet_run[i - 1] - quiet_run[i - 1 - rest] < rest:  # not dark long enough
            continue
        frac = (thr - x[i - 1]) / (x[i] - x[i - 1])
        out.append(i - 1 + frac)
    return np.array(out)


def peak_freq(x: np.ndarray, fs: float, fmin: float = 3.0, fmax: float = 70.0) -> float:
    x = np.nan_to_num(x - np.nanmean(x))
    n = max(len(x) * 8, 4096)
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), n))
    f = np.fft.rfftfreq(n, 1 / fs)
    band = (f >= fmin) & (f <= fmax)
    return float(f[band][np.argmax(spec[band])])


def host_clock_fit(rec: Record) -> tuple[float, float]:
    """time = a + b * index, shifted to the earliest-arriving packets (least link delay)."""
    idx, t = rec.packet_index.astype(float), rec.packet_time
    b, a = np.polyfit(idx, t, 1)
    a += np.min(t - (a + b * idx))
    return a, b


def match_trials(rec: Record, events: list[dict], levels: tuple[float, float] | None = None,
                 tol_s: float = 0.3) -> tuple[list[Trial], list[str]]:
    """Pair photodiode onsets with the stimulus log. Uses the host clock only to pick
    which onset belongs to which logged trial; the onset time itself is the photodiode's."""
    notes: list[str] = []
    pd = rec.channel(P.PD_CHANNEL)
    onsets = pd_onsets(pd, rec.fs, levels=levels)
    stims = [e for e in events if e["kind"] == "stim_start"]
    rests = {e["trial"]: e for e in events if e["kind"] == "rest_start"}
    drops = {k: e.get("drops_in_stim", 0) for k, e in rests.items()}
    if not stims:
        return [], ["no stim_start events in the log"]
    if len(onsets) != len(stims):
        notes.append(f"{len(onsets)} photodiode onsets for {len(stims)} logged trials")

    a, b = host_clock_fit(rec)
    predicted = np.array([(e["t_swap"] - a) / b for e in stims])
    if len(onsets):
        nearest = np.array([onsets[np.argmin(np.abs(onsets - p))] for p in predicted])
        lag = float(np.median(nearest - predicted))
    else:
        lag = 0.0

    trials = []
    used = set()
    for e, p in zip(stims, predicted):
        if not len(onsets):
            break
        j = int(np.argmin(np.abs(onsets - (p + lag))))
        if abs(onsets[j] - (p + lag)) > tol_s * rec.fs or j in used:
            notes.append(f"trial {e['trial']}: no photodiode onset near the logged time")
            continue
        used.add(j)
        on = onsets[j]
        stim_s = rests[e["trial"]]["t_swap"] - e["t_swap"] if e["trial"] in rests else 1.0
        seg = pd[int(on + 0.1 * rec.fs): int(on + (stim_s - 0.05) * rec.fs)]
        mf = peak_freq(seg, rec.fs) if len(seg) > rec.fs * 0.5 else float("nan")
        if abs(mf - e["freq"]) > 0.25:
            notes.append(f"trial {e['trial']}: photodiode shows {mf:.2f} Hz, log says {e['freq']:.2f} Hz")
        trials.append(Trial(e["trial"], e["target"], e["freq"], float(on), mf,
                            drops.get(e["trial"], 0), (on - p) / rec.fs * 1e3))
    return trials, notes


def epochs(rec: Record, trials: list[Trial], length_s: float, delay_s: float = 0.14,
           channels=P.EEG_CHANNELS) -> tuple[np.ndarray, np.ndarray]:
    """(trials, channels, samples) EEG starting `delay_s` after each onset (visual latency)."""
    n = int(length_s * rec.fs)
    cols = [rec.channels.index(c) for c in channels]
    X, y = [], []
    for t in trials:
        s = int(round(t.onset + delay_s * rec.fs))
        seg = rec.data[s:s + n, cols]
        if len(seg) < n:
            continue
        if np.isnan(seg).any():  # lost samples: bridge short gaps linearly
            for k in range(seg.shape[1]):
                col = seg[:, k]
                bad = np.isnan(col)
                col[bad] = np.interp(np.flatnonzero(bad), np.flatnonzero(~bad), col[~bad])
        X.append(seg.T)
        y.append(t.target)
    return np.array(X), np.array(y)
