"""Frame-locked stimulus window. Runs in its own process with its own QApplication so
plots, BLE and file writes in the control window can never delay a frame.

Timing rule: every luminance is a function of the vsync index, the number of refresh
periods since the schedule began, at which that frame will be on screen. Painting
happens on frameSwapped. When the system misses vsyncs (Windows does, ~16 ms stalls),
the next frame jumps ahead to the right index: the stall shows as one frame held
longer, but frequency and phase stay exact. Missed vsyncs are counted as drops, and
the photodiode records what the screen really did.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import numpy as np

from .config import StimConfig

MEASURE_FRAMES = 120


@dataclass
class Segment:
    kind: str     # "lead", "cue", "stim", "rest", "white", "black"
    start: int    # frame index (relative to schedule start)
    frames: int
    trial: int = -1
    target: int = -1


def build_schedule(cfg: StimConfig, refresh: float) -> tuple[list[Segment], list[int]]:
    def nf(seconds: float) -> int:
        return max(1, round(seconds * refresh))

    order = cfg.trial_order()
    segs: list[Segment] = []
    t = 0
    for kind, frames, trial, target in [("lead", nf(cfg.lead_in_s), -1, -1)] + [
        x for k, tgt in enumerate(order)
        for x in (("cue", nf(cfg.cue_s), k, tgt), ("stim", nf(cfg.stim_s), k, tgt),
                  ("rest", nf(cfg.rest_s), k, tgt))
    ]:
        segs.append(Segment(kind, t, frames, trial, target))
        t += frames
    return segs, order


def calibration_schedule(refresh: float, cycles: int = 3, seconds: float = 2.0) -> list[Segment]:
    n = round(seconds * refresh)
    segs, t = [Segment("black", 0, n)], n
    for _ in range(cycles):
        segs += [Segment("white", t, n), Segment("black", t + n, n)]
        t += 2 * n
    return segs


def estimate_period(times: list[float], nominal_hz: float = 0.0) -> float:
    """Refresh period from swap times that may include stalls: take the typical interval
    near the nominal rate, number every swap on that vsync grid, and fit the slope."""
    t = np.asarray(times, dtype=float)
    d = np.diff(t)
    p0 = 1.0 / nominal_hz if nominal_hz > 0 else float(np.median(d))
    near = d[(d > 0.75 * p0) & (d < 1.25 * p0)]
    p0 = float(np.median(near)) if len(near) >= 10 else float(np.median(d))
    # Number swaps from their neighbours (each gap is a small whole number of periods),
    # so an error in p0 cannot accumulate across the record.
    n = np.concatenate([[0], np.cumsum(np.maximum(1, np.round(d / p0)))])
    return float(np.polyfit(n, t, 1)[0])


def target_luminance(freq: float, phase: float, frame: int, refresh: float) -> float:
    return 0.5 * (1 + math.sin(2 * math.pi * freq * frame / refresh + phase))


def run_stimulus(mode: str, cfg_dict: dict, events, abort, luminance=None) -> None:
    """Process entry point. mode: "session" or "calibrate". Events go to `events`
    (a multiprocessing.Queue) as dicts; setting `abort` (an Event) ends the run."""
    from PyQt6.QtCore import QRectF, Qt, QTimer
    from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen, QSurfaceFormat
    from PyQt6.QtOpenGL import QOpenGLWindow

    cfg = StimConfig.from_dict(cfg_dict)

    fmt = QSurfaceFormat()
    fmt.setSwapInterval(1)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QGuiApplication([])

    def send(kind: str, **kw) -> None:
        events.put(dict(kind=kind, **kw))

    class StimWindow(QOpenGLWindow):
        def __init__(self) -> None:
            super().__init__()
            self.frame = -1               # frames painted since the window opened
            self.refresh = 0.0
            self.period = 0.0
            self.t_origin = 0.0           # when schedule frame 0 is on screen
            self.last_f = -1
            self.swap_times: list[float] = []
            self.schedule: list[Segment] = []
            self.seg_i = -1
            self.pending: list[dict] = [] # events for the frame being painted
            self.drops = 0
            self.trial_drops = 0
            self.frameSwapped.connect(self.on_swapped)

        # -- timing ------------------------------------------------------------
        def on_swapped(self) -> None:
            t = time.perf_counter()
            self.swap_times.append(t)
            for ev in self.pending:
                ev["t_swap"] = t
                events.put(ev)
            self.pending = []

            if abort.is_set():
                send("aborted", frame=self.frame, drops=self.drops)
                app.quit()
                return
            if not self.refresh and len(self.swap_times) >= MEASURE_FRAMES:
                self.start_schedule()
            self.update()  # next frame, painted after this vsync

        def start_schedule(self) -> None:
            # Windows reports the panel's exact rate; swap callbacks are jittery under
            # stalls, so the measurement is only a check that vsync is really on.
            nominal = self.screen().refreshRate()
            measured = 1.0 / estimate_period(self.swap_times[10:], nominal)
            use_nominal = nominal > 0 and abs(measured / nominal - 1) < 0.03
            self.refresh = nominal if use_nominal else measured
            self.period = 1.0 / self.refresh
            self.t_origin = self.swap_times[-1] + self.period
            self.first_sched_paint = self.frame
            if mode == "calibrate":
                self.schedule = calibration_schedule(self.refresh)
                order = []
            else:
                self.schedule, order = build_schedule(cfg, self.refresh)
            self.drops = 0
            send("refresh", hz=self.refresh, measured_hz=measured, nominal_hz=nominal,
                 vsync_ok=use_nominal, order=order,
                 targets=[t.__dict__ for t in cfg.targets], mode=mode)

        # -- drawing -----------------------------------------------------------
        def segment_at(self, f: int) -> Segment | None:
            while self.seg_i + 1 < len(self.schedule) and self.schedule[self.seg_i + 1].start <= f:
                self.seg_i += 1
                seg = self.schedule[self.seg_i]
                ev = dict(kind=seg.kind + "_start", frame=f, trial=seg.trial, target=seg.target)
                if seg.kind == "stim":
                    tgt = cfg.targets[seg.target]
                    ev.update(freq=tgt.freq, phase=tgt.phase)
                    self.trial_drops = 0
                if seg.kind == "rest" and seg.trial >= 0:
                    ev["drops_in_stim"] = self.trial_drops
                self.pending.append(ev)
            if self.seg_i < 0:
                return None
            seg = self.schedule[self.seg_i]
            if f >= seg.start + seg.frames:
                return None
            return seg

        def level(self, lum: float) -> QColor:
            v = max(0.0, min(1.0, lum)) ** (1.0 / cfg.gamma)
            return QColor.fromRgbF(v, v, v)

        def paintGL(self) -> None:
            self.frame += 1
            p = QPainter(self)
            w, h = self.width(), self.height()
            p.fillRect(0, 0, w, h, QColor(0, 0, 0))
            patch = 0.0

            if self.refresh:
                # Index of the vsync this frame will appear on.
                f = round((self.swap_times[-1] + self.period - self.t_origin) / self.period)
                f = max(f, self.last_f + 1)
                if self.last_f >= 0 and f > self.last_f + 1:
                    self.drops += f - self.last_f - 1
                    self.trial_drops += f - self.last_f - 1
                self.last_f = f
                seg = self.segment_at(f)
                if seg is None:
                    if not self.pending:
                        send("done", frame=f, drops=self.drops,
                             painted=self.frame - self.first_sched_paint)
                        p.end()
                        QTimer.singleShot(0, app.quit)
                        return
                elif mode == "calibrate":
                    patch = 1.0 if seg.kind == "white" else 0.0
                else:
                    patch = self.draw_targets(p, seg, f, w, h)
            else:
                p.setPen(QColor(90, 90, 90))
                p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "measuring refresh rate…")

            self.draw_patch(p, patch, w, h)
            p.end()
            if luminance is not None:
                luminance.value = patch

        def draw_targets(self, p: QPainter, seg: Segment, f: int, w: int, h: int) -> float:
            patch = 0.0
            for i, tgt in enumerate(cfg.targets):
                side = tgt.size * h
                rect = QRectF(tgt.x * w - side / 2, tgt.y * h - side / 2, side, side)
                if seg.kind == "stim":
                    lum = target_luminance(tgt.freq, tgt.phase, f - seg.start, self.refresh)
                    if i == seg.target:
                        marker = f - seg.start < cfg.onset_marker_frames
                        patch = 1.0 if marker else lum
                elif seg.kind == "lead":
                    lum = 0.0
                else:
                    lum = cfg.idle_level
                p.fillRect(rect, self.level(lum))
                if seg.kind == "cue" and i == seg.target:
                    pen = QPen(QColor(220, 40, 40))
                    pen.setWidthF(max(4.0, side * 0.04))
                    p.setPen(pen)
                    p.drawRect(rect.adjusted(-side * 0.08, -side * 0.08, side * 0.08, side * 0.08))
            return patch

        def draw_patch(self, p: QPainter, lum: float, w: int, h: int) -> None:
            s = cfg.patch_px
            x = 0 if "left" in cfg.patch_corner else w - s
            y = 0 if "top" in cfg.patch_corner else h - s
            p.fillRect(x, y, s, s, self.level(lum))

        def keyPressEvent(self, e) -> None:
            if e.key() == Qt.Key.Key_Escape:
                abort.set()

    win = StimWindow()
    screens = QGuiApplication.screens()
    screen = screens[min(cfg.screen, len(screens) - 1)]
    win.setScreen(screen)
    if cfg.windowed:
        win.resize(640, 360)
        win.show()
    else:
        win.setGeometry(screen.geometry())
        win.setCursor(Qt.CursorShape.BlankCursor)
        win.showFullScreen()
    app.exec()
