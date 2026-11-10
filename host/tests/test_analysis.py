"""Synthetic session through the real recorder and analysis: onsets must land on the
frame the stimulus started, and FBCCA must find the cued frequency."""

import numpy as np
import pytest

from ssvep_host import protocol as P
from ssvep_host.analysis import analyse
from ssvep_host.analysis.cca import classify
from ssvep_host.analysis.epochs import pd_onsets
from ssvep_host.recorder import Recorder
from ssvep_host.stim.config import StimConfig, grid_targets
from ssvep_host.stim.window import build_schedule, target_luminance

FS = P.sample_rate(8e6, 6)
REFRESH = 60.0


def synth_session(tmp_path, freqs=(8.0, 10.0, 12.0, 15.0), reps=2, lost=()):
    cfg = StimConfig(targets=grid_targets(list(freqs)), stim_s=3.0, trials_per_target=reps, seed=1)
    segs, order = build_schedule(cfg, REFRESH)
    n_frames = segs[-1].start + segs[-1].frames
    t0 = 0.0  # host time of frame 0; samples start 0.5 s before it
    n = int((n_frames / REFRESH + 1.5) * FS)
    t = np.arange(n) / FS - 0.5
    frame = np.floor(t * REFRESH).astype(int)

    patch = np.zeros(n)
    eeg = np.random.default_rng(0).normal(0, 3, (n, 4))
    events = [dict(kind="refresh", hz=REFRESH, order=order, targets=[x.__dict__ for x in cfg.targets])]
    for s in segs:
        if s.kind != "stim":
            continue
        tgt = cfg.targets[s.target]
        events.append(dict(kind="stim_start", frame=s.start, trial=s.trial, target=s.target,
                           freq=tgt.freq, phase=tgt.phase, t_swap=t0 + s.start / REFRESH))
        events.append(dict(kind="rest_start", trial=s.trial, drops_in_stim=0,
                           t_swap=t0 + (s.start + s.frames) / REFRESH))
        on = (frame >= s.start) & (frame < s.start + s.frames)
        k = frame[on] - s.start
        lum = np.array([target_luminance(tgt.freq, tgt.phase, int(i), REFRESH, cfg.waveform)
                        for i in k])
        lum[k < cfg.onset_marker_frames] = 1.0
        patch[on] = lum
        # SSVEP 140 ms after the light, 2 uV, in all four channels
        resp = np.sin(2 * np.pi * tgt.freq * (t[on] - 0.14))
        eeg[on] += 2.0 * resp[:, None]

    pd_v = 0.02 + 0.9 * patch
    volts = np.zeros((n, 5))
    volts[:, :4] = eeg * 1e-6 * P.INA_GAIN
    volts[:, 4] = pd_v
    codes = np.round(volts / P.volts_per_code(0)).astype(np.int32)

    rec = Recorder(tmp_path)
    rec.start(dict(stim=cfg.to_dict(), pd_levels=None))
    per = 15
    for i in range(0, n, per):
        idx = np.arange(i, min(n, i + per))
        keep = ~np.isin(idx, lost)
        if not keep.any():
            continue
        # packets arrive 30 ms after their last sample
        pkt = P.DataPacket(int(idx[keep][0]), 0x1F, 0, codes[idx[keep]])
        if not keep.all():  # split around the hole like the firmware would
            for run in np.split(idx[keep], np.flatnonzero(np.diff(idx[keep]) > 1) + 1):
                rec.add_packet(t[run[-1]] + 0.03, P.DataPacket(int(run[0]), 0x1F, 0, codes[run]))
            continue
        rec.add_packet(t[idx[-1]] + 0.03, pkt)
    for e in events:
        rec.add_event(e)
    status = P.Status(1, 0, 6, 3900, 0x2802, 8000, n, 0, 0, 0x1F, 0)
    return rec.stop(status), segs, t


def test_onsets_hit_stimulus_frames(tmp_path):
    folder, segs, t = synth_session(tmp_path)
    r = analyse(folder)
    starts = [s.start for s in segs if s.kind == "stim"]
    assert len(r["trials"]) == len(starts)
    for tr, f in zip(r["trials"], starts):
        expected = (f / REFRESH + 0.5) * FS  # sample index of the frame
        assert abs(tr.onset - expected) < 1.5
        assert tr.measured_freq == pytest.approx(tr.freq, abs=0.2)
    assert r["notes"] == []


def test_fbcca_finds_cued_target(tmp_path):
    folder, _, _ = synth_session(tmp_path)
    r = analyse(folder)
    assert r["accuracy"] >= 0.85


def test_lost_samples_are_bridged(tmp_path):
    folder, segs, _ = synth_session(tmp_path, lost=np.arange(5000, 5040))
    r = analyse(folder)
    assert len(r["trials"]) == sum(s.kind == "stim" for s in segs)


def test_onset_needs_darkness_before():
    pd = np.r_[np.zeros(500), np.ones(100), np.zeros(10), np.ones(100), np.zeros(500)]
    on = pd_onsets(pd, FS, min_rest_s=0.5)
    assert len(on) == 1 and abs(on[0] - 499.5) < 1


def test_cca_on_pure_sines():
    fs, n = 500.0, 1000
    t = np.arange(n) / fs
    freqs = [8.0, 10.0, 12.0]
    X = np.stack([np.stack([np.sin(2 * np.pi * f * t + c) for c in range(3)]) for f in freqs])
    X += np.random.default_rng(1).normal(0, 0.5, X.shape)
    assert list(classify(X, freqs, fs, "cca")) == [0, 1, 2]
    assert list(classify(X, freqs, fs, "fbcca")) == [0, 1, 2]


def test_period_estimate_survives_stalls():
    from ssvep_host.stim.window import estimate_period
    rng = np.random.default_rng(2)
    period = 1 / 239.76
    k = np.cumsum(np.where(rng.random(400) < 0.2, 4, 1))  # 20% of swaps miss 3 vsyncs
    times = 100.0 + k * period + rng.normal(0, 2e-4, len(k))
    assert estimate_period(list(times), 240.0) == pytest.approx(period, rel=1e-4)
    assert estimate_period(list(times)) == pytest.approx(period, rel=1e-4)


def test_square_wave_is_even_on_divisors():
    from ssvep_host.stim.window import uneven_frequencies
    lum = [target_luminance(15.0, 0.0, f, 240.0, "square") for f in range(32)]
    assert lum == [1.0] * 8 + [0.0] * 8 + [1.0] * 8 + [0.0] * 8
    assert uneven_frequencies([8, 10, 12, 15, 20, 24], 240.0) == []
    assert uneven_frequencies([8, 10, 12, 15], 60.0) == [8, 12]  # 7.5 and 5 frames per cycle
    assert uneven_frequencies([11.3], 240.0) == [11.3]


@pytest.mark.parametrize("n", [1, 2, 3, 4, 6, 8])
@pytest.mark.parametrize("corner", ["bottom-left", "top-right"])
def test_corner_layout_clears_patch(n, corner):
    from ssvep_host.stim.window import target_rects
    w, h, s = 2048, 1280, 60
    cfg = StimConfig(targets=grid_targets([10.0 + i for i in range(n)]), patch_corner=corner, patch_px=s)
    rects = target_rects(cfg, w, h)
    px = 0 if "left" in corner else w - s
    py = 0 if "top" in corner else h - s
    for x, y, side in rects:
        assert 0 <= x and x + side <= w and 0 <= y and y + side <= h
        gap_x = max(px - (x + side), x - (px + s))
        gap_y = max(py - (y + side), y - (py + s))
        assert max(gap_x, gap_y) >= s  # at least a patch width of black
    for i, (x1, y1, s1) in enumerate(rects):
        for x2, y2, s2 in rects[i + 1:]:
            assert x1 + s1 <= x2 or x2 + s2 <= x1 or y1 + s1 <= y2 or y2 + s2 <= y1
