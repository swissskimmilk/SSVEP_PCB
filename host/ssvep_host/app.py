"""Control window: connect to the board, watch signals, calibrate the photodiode, and
run stimulus sessions. The stimulus itself runs in a separate process (stim/window.py)."""

from __future__ import annotations

import concurrent.futures as cf
import multiprocessing as mp
import queue
import time
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                             QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                             QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QVBoxLayout, QWidget)
from scipy.signal import butter, iirnotch, sosfiltfilt, tf2sos, welch

from . import protocol as P
from .analysis import analyse
from .device import BleDevice, Device, SerialDevice, SimDevice
from .recorder import Recorder
from .stim.config import StimConfig, grid_targets
from .stim.window import run_stimulus

SESSIONS = Path(__file__).resolve().parent.parent / "sessions"
DISPLAY_S = 10.0
BUFFER_S = 15.0
CH_NAMES = {0: "EEG 1", 1: "EEG 2", 2: "EEG 3", 3: "EEG 4", 4: "Photodiode"}


class Scope:
    """Rolling buffer of scaled samples for the plots."""

    def __init__(self) -> None:
        self.reset([], 1.0)

    def reset(self, channels: list[int], fs: float) -> None:
        self.channels = channels
        self.fs = fs
        self.n = int(BUFFER_S * max(fs, 1))
        self.buf = np.full((self.n, len(channels)), np.nan)
        self.count = 0

    def add(self, values: np.ndarray) -> None:
        k = len(values)
        if k >= self.n:
            self.buf[:] = values[-self.n:]
        else:
            self.buf = np.roll(self.buf, -k, axis=0)
            self.buf[-k:] = values
        self.count += k

    def last(self, seconds: float) -> np.ndarray:
        return self.buf[-int(seconds * self.fs):]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SSVEP control")
        self.ctx = mp.get_context("spawn")
        self.luminance = self.ctx.Value("d", 0.0)
        self.device: Device | None = None
        self.status: P.Status | None = None
        self.scope = Scope()
        self.recorder = Recorder(SESSIONS)
        self.pool = cf.ThreadPoolExecutor(max_workers=1)
        self.pending: cf.Future | None = None
        self.pending_kind = ""
        self.stim_proc = None
        self.stim_events = None
        self.stim_abort = None
        self.stim_mode = ""
        self.stim_done_at = 0.0
        self.calib: list[np.ndarray] = []
        self.pd_levels: tuple[float, float] | None = None
        self.n_trials = 0

        self._build()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(50)

    # ---------------------------------------------------------------- layout

    def _build(self) -> None:
        left = QVBoxLayout()

        board = QGroupBox("Board")
        f = QFormLayout(board)
        self.source = QComboBox()
        self.source.addItems(["Simulator", "BLE", "USB serial (bench only)"])
        self.source.currentIndexChanged.connect(self.source_changed)
        self.address = QComboBox()
        self.address.setEditable(True)
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self.scan)
        row = QHBoxLayout()
        row.addWidget(self.address, 1)
        row.addWidget(self.scan_btn)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connect)
        self.stream_btn = QPushButton("Start stream")
        self.stream_btn.clicked.connect(self.toggle_stream)
        self.off_btn = QPushButton("Analog off")
        self.off_btn.clicked.connect(lambda: self.send(P.CMD_ANALOG_OFF))
        f.addRow("Link", self.source)
        f.addRow("Device", row)
        f.addRow(self.connect_btn)
        btns = QHBoxLayout()
        btns.addWidget(self.stream_btn)
        btns.addWidget(self.off_btn)
        f.addRow(btns)
        left.addWidget(board)

        self.adc_box = QGroupBox("ADC")
        g = QGridLayout(self.adc_box)
        self.osr = QComboBox()
        for code in (5, 6, 7):
            self.osr.addItem(f"OSR {P.OSR_VALUES[code]} ({P.sample_rate(8e6, code):.1f} SPS)", code)
        self.osr.setCurrentIndex(1)
        self.osr.activated.connect(lambda _: self.send(P.CMD_SET_OSR, self.osr.currentData()))
        g.addWidget(QLabel("Rate"), 0, 0)
        g.addWidget(self.osr, 0, 1, 1, 2)
        self.gain_boxes, self.mux_boxes = [], []
        for i, ch in enumerate(range(5)):
            gain = QComboBox()
            gain.addItems([f"x{1 << c}" for c in range(8)])
            gain.activated.connect(lambda c, ch=ch: self.send(P.CMD_SET_GAIN, ch, c))
            mux = QComboBox()
            mux.addItems(P.MUX_NAMES)
            mux.activated.connect(lambda m, ch=ch: self.send(P.CMD_SET_MUX, ch, m))
            g.addWidget(QLabel(CH_NAMES[ch]), i + 1, 0)
            g.addWidget(gain, i + 1, 1)
            g.addWidget(mux, i + 1, 2)
            self.gain_boxes.append(gain)
            self.mux_boxes.append(mux)
        left.addWidget(self.adc_box)

        st = QGroupBox("Status")
        f = QFormLayout(st)
        self.lbl = {k: QLabel("–") for k in ("battery", "rate", "samples", "dropped", "crc", "error")}
        for k, w in self.lbl.items():
            f.addRow(k.capitalize(), w)
        self.vbus = QLabel("USB power present: the board is tied to the laptop.\n"
                           "Do not connect electrodes to a person.")
        self.vbus.setStyleSheet("color: white; background: #b00020; padding: 4px; font-weight: bold;")
        self.vbus.setVisible(False)
        f.addRow(self.vbus)
        left.addWidget(st)

        stim = QGroupBox("Stimulus")
        f = QFormLayout(stim)
        self.freqs = QLineEdit("8, 10, 12, 15")
        self.cue = self._spin(1.0, 0, 5)
        self.stim_s = self._spin(4.0, 0.5, 30)
        self.rest = self._spin(1.5, 0.6, 10)
        self.reps = QSpinBox()
        self.reps.setRange(1, 100)
        self.reps.setValue(5)
        self.screen = QComboBox()
        for i, s in enumerate(QGuiApplication.screens()):
            g_ = s.geometry()
            self.screen.addItem(f"{i}: {s.name()} {g_.width()}x{g_.height()} {s.refreshRate():.0f} Hz")
        self.corner = QComboBox()
        self.corner.addItems(["bottom-left", "bottom-right", "top-left", "top-right"])
        self.patch_px = QSpinBox()
        self.patch_px.setRange(20, 400)
        self.patch_px.setValue(60)
        self.gamma = self._spin(1.0, 1.0, 3.0)
        self.windowed = QCheckBox("Windowed (testing only)")
        f.addRow("Frequencies (Hz)", self.freqs)
        f.addRow("Cue / stim / rest (s)", self._hbox(self.cue, self.stim_s, self.rest))
        f.addRow("Trials per target", self.reps)
        f.addRow("Screen", self.screen)
        f.addRow("Sync patch", self._hbox(self.corner, self.patch_px))
        f.addRow("Display gamma", self.gamma)
        f.addRow(self.windowed)
        self.calib_btn = QPushButton("Calibrate photodiode")
        self.calib_btn.clicked.connect(lambda: self.start_stim("calibrate"))
        self.session_btn = QPushButton("Start session")
        self.session_btn.clicked.connect(lambda: self.start_stim("session"))
        self.abort_btn = QPushButton("Abort")
        self.abort_btn.clicked.connect(self.abort_stim)
        self.abort_btn.setEnabled(False)
        f.addRow(self._hbox(self.calib_btn, self.session_btn, self.abort_btn))
        self.progress = QLabel("")
        f.addRow(self.progress)
        left.addWidget(stim)
        left.addStretch(1)

        panel = QWidget()
        panel.setLayout(left)
        panel.setFixedWidth(400)

        right = QVBoxLayout()
        top = QHBoxLayout()
        self.filt = QCheckBox("Display filter: 1–45 Hz + 60 Hz notch")
        self.filt.setChecked(True)
        top.addWidget(self.filt)
        top.addStretch(1)
        right.addLayout(top)
        pg.setConfigOptions(antialias=False)
        self.plots = pg.GraphicsLayoutWidget()
        self.curves: dict[int, pg.PlotDataItem] = {}
        for i, ch in enumerate(range(5)):
            p = self.plots.addPlot(row=i, col=0)
            p.setLabel("left", CH_NAMES[ch], units="V" if ch == P.PD_CHANNEL else "µV")
            p.showGrid(x=True, y=True, alpha=0.2)
            p.setMouseEnabled(x=False)
            if i:
                p.setXLink(self.plots.getItem(0, 0))
            self.curves[ch] = p.plot(pen=pg.intColor(i, 6))
        self.psd = self.plots.addPlot(row=0, col=1, rowspan=5)
        self.psd.setLabel("bottom", "Hz")
        self.psd.setLabel("left", "PSD", units="µV²/Hz")
        self.psd.setLogMode(y=True)
        self.psd.setXRange(0, 50)
        self.psd.addLegend()
        self.psd_curves = {ch: self.psd.plot(pen=pg.intColor(ch, 6), name=CH_NAMES[ch])
                           for ch in P.EEG_CHANNELS}
        self.plots.ci.layout.setColumnStretchFactor(0, 3)
        self.plots.ci.layout.setColumnStretchFactor(1, 1)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.plots)
        split.addWidget(self.log)
        split.setSizes([700, 150])
        right.addWidget(split)

        root = QHBoxLayout()
        root.addWidget(panel)
        root.addLayout(right, 1)
        w = QWidget()
        w.setLayout(root)
        self.setCentralWidget(w)
        self.resize(1500, 950)
        self.source_changed()
        self.update_buttons()

    @staticmethod
    def _spin(v: float, lo: float, hi: float) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(0.1)
        s.setValue(v)
        return s

    @staticmethod
    def _hbox(*ws) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        for x in ws:
            lay.addWidget(x)
        return w

    def say(self, msg: str) -> None:
        self.log.appendPlainText(time.strftime("%H:%M:%S  ") + msg)

    # ---------------------------------------------------------------- device

    def source_changed(self) -> None:
        kind = self.source.currentIndex()
        self.address.clear()
        self.scan_btn.setEnabled(kind != 0)
        self.address.setEnabled(kind != 0)
        if kind == 2:
            self.address.addItems(SerialDevice.ports())

    def scan(self) -> None:
        if self.source.currentIndex() == 2:
            self.source_changed()
            return
        self.say("scanning for BLE boards…")
        self.run_async("scan", BleDevice.scan)

    def run_async(self, kind: str, fn, *args) -> None:
        self.pending_kind = kind
        self.pending = self.pool.submit(fn, *args)
        self.update_buttons()

    def toggle_connect(self) -> None:
        if self.device and self.device.connected:
            if self.stim_proc:
                self.abort_stim()
            self.device.disconnect()
            self.device = None
            self.say("disconnected")
            self.update_buttons()
            return
        kind = self.source.currentIndex()
        if kind == 0:
            dev = SimDevice(self.luminance)
        elif kind == 1:
            addr = self.address.currentData() or self.address.currentText()
            if not addr:
                self.say("scan first or type the board's address")
                return
            dev = BleDevice(addr)
        else:
            dev = SerialDevice(self.address.currentText())
            self.say("USB link: bench use only, never with electrodes on a person")
        self.device = dev
        self.run_async("connect", dev.connect)

    def send(self, op: int, *args: int) -> None:
        if self.device and self.device.connected:
            try:
                self.device.send(P.command(op, *args))
            except Exception as e:
                self.say(f"send failed: {e}")

    def toggle_stream(self) -> None:
        streaming = self.status and self.status.has(P.STATUS_FLAG_STREAMING)
        self.send(P.CMD_STOP if streaming else P.CMD_START)

    def update_buttons(self) -> None:
        busy = self.pending is not None
        conn = bool(self.device and self.device.connected)
        streaming = bool(self.status and self.status.has(P.STATUS_FLAG_STREAMING)) and conn
        stim = self.stim_proc is not None
        self.connect_btn.setText("Disconnect" if conn else "Connect")
        self.connect_btn.setEnabled(not busy)
        self.stream_btn.setText("Stop stream" if streaming else "Start stream")
        self.stream_btn.setEnabled(conn and not stim)
        self.off_btn.setEnabled(conn and not stim)
        self.adc_box.setEnabled(conn and not stim)
        self.source.setEnabled(not conn and not busy)
        self.calib_btn.setEnabled(streaming and not stim)
        self.session_btn.setEnabled(streaming and not stim)
        self.abort_btn.setEnabled(stim)

    # ---------------------------------------------------------------- stimulus

    def stim_config(self) -> StimConfig:
        freqs = [float(x) for x in self.freqs.text().replace(";", ",").split(",") if x.strip()]
        return StimConfig(targets=grid_targets(freqs), cue_s=self.cue.value(),
                          stim_s=self.stim_s.value(), rest_s=self.rest.value(),
                          trials_per_target=self.reps.value(), screen=self.screen.currentIndex(),
                          patch_corner=self.corner.currentText(), patch_px=self.patch_px.value(),
                          gamma=self.gamma.value(), windowed=self.windowed.isChecked())

    def start_stim(self, mode: str) -> None:
        try:
            cfg = self.stim_config()
        except ValueError:
            self.say("frequencies must be numbers separated by commas")
            return
        if mode == "session":
            if not cfg.targets:
                self.say("no frequencies given")
                return
            if self.pd_levels is None:
                self.say("photodiode not calibrated: onsets will use automatic levels")
            folder = self.recorder.start(dict(stim=cfg.to_dict(), pd_levels=self.pd_levels,
                                              link=self.source.currentText()))
            self.n_trials = len(cfg.targets) * cfg.trials_per_target
            self.say(f"recording to {folder}")
        else:
            self.calib = []
        self.stim_mode = mode
        self.stim_events = self.ctx.Queue()
        self.stim_abort = self.ctx.Event()
        self.stim_proc = self.ctx.Process(
            target=run_stimulus, daemon=True,
            args=(mode, cfg.to_dict(), self.stim_events, self.stim_abort, self.luminance))
        self.stim_proc.start()
        self.stim_done_at = 0.0
        self.update_buttons()

    def abort_stim(self) -> None:
        if self.stim_abort is not None:
            self.stim_abort.set()

    def stim_event(self, ev: dict) -> None:
        if self.stim_mode == "session":
            self.recorder.add_event(ev)
        kind = ev["kind"]
        if kind == "refresh":
            self.say(f"display {ev['hz']:.3f} Hz (measured {ev['measured_hz']:.2f})")
            if not ev["vsync_ok"]:
                self.say("  measured rate disagrees with the display's: vsync may be off "
                         "(check the GPU driver's vsync setting)")
        elif kind == "stim_start":
            self.progress.setText(f"trial {ev['trial'] + 1}/{self.n_trials}: {ev['freq']:g} Hz")
        elif kind == "rest_start" and ev.get("drops_in_stim"):
            self.say(f"trial {ev['trial']}: {ev['drops_in_stim']} dropped frame(s)")
        elif kind in ("done", "aborted"):
            self.say(f"stimulus {kind}: {ev.get('drops', 0)} of {ev.get('frame', 0)} vsyncs missed")
            self.stim_done_at = time.perf_counter()

    def finish_stim(self) -> None:
        mode = self.stim_mode
        self.stim_proc.join(2)
        if not self.stim_done_at:
            self.say(f"stimulus window exited unexpectedly (exit code {self.stim_proc.exitcode})")
        self.stim_proc = None
        self.progress.setText("")
        if mode == "session":
            folder = self.recorder.stop(self.status)
            self.say(f"saved {folder}")
            try:
                r = analyse(folder)
                for n in r["notes"]:
                    self.say("  " + n)
                lags = [t.host_offset_ms for t in r["trials"]]
                if lags:
                    self.say(f"  {len(r['trials'])} trials matched, display+link lag "
                             f"{np.median(lags):.0f} ms (informational)")
                if len(r["y"]):
                    self.say(f"  FBCCA accuracy {r['accuracy'] * 100:.0f}% on {len(r['y'])} trials")
            except Exception as e:
                self.say(f"  analysis failed: {e}")
        elif mode == "calibrate":
            self.finish_calibration()
        self.update_buttons()

    def finish_calibration(self) -> None:
        if not self.calib:
            self.say("calibration: no photodiode data (is the stream running?)")
            return
        pd = np.concatenate(self.calib)
        pd = pd[np.isfinite(pd)]
        lo, hi = float(np.percentile(pd, 5)), float(np.percentile(pd, 95))
        self.say(f"photodiode: black {lo * 1e3:.1f} mV, white {hi * 1e3:.1f} mV")
        if hi > 1.1:
            self.say("  white is near the ADC's 1.2 V full scale: lower R3 (photodiode load)")
        if hi - lo < 0.05:
            self.say("  swing under 50 mV: check the photodiode sits on the patch, or raise R3")
            return
        self.pd_levels = (lo, hi)

    # ---------------------------------------------------------------- loop

    def tick(self) -> None:
        if self.pending is not None and self.pending.done():
            fut, kind = self.pending, self.pending_kind
            self.pending = None
            try:
                result = fut.result()
                if kind == "scan":
                    self.address.clear()
                    for name, addr in result:
                        self.address.addItem(f"{name}  {addr}", addr)
                    self.say(f"found {len(result)} board(s)")
                elif kind == "connect":
                    self.say("connected")
                    self.send(P.CMD_STATUS)
            except Exception as e:
                self.say(f"{kind} failed: {e}")
                if kind == "connect":
                    self.device = None
            self.update_buttons()

        if self.device is not None:
            if self.device.error:
                self.say(self.device.error)
                self.device.error = ""
            self.drain()

        if self.stim_proc is not None:
            while True:
                try:
                    self.stim_event(self.stim_events.get_nowait())
                except queue.Empty:
                    break
            # Keep recording ~1 s after the last frame so the final epoch is complete.
            ended = self.stim_done_at and time.perf_counter() - self.stim_done_at > 1.0
            if ended or (not self.stim_proc.is_alive() and not self.stim_done_at):
                self.finish_stim()

        self.redraw()

    def drain(self) -> None:
        dev = self.device
        changed = False
        while True:
            try:
                t, msg = dev.packets.get_nowait()
            except queue.Empty:
                break
            if isinstance(msg, P.Status):
                was = self.status
                self.status = msg
                self.show_status(msg)
                changed = changed or was is None or was.flags != msg.flags or was.fs != msg.fs
            else:
                if self.scope.channels != msg.channels or (self.status and self.scope.fs != self.status.fs):
                    self.scope.reset(msg.channels, self.status.fs if self.status else 488.28)
                scaled = msg.samples * P.scale_to_units(msg.channels, self.status.gain if self.status else [0] * 8)
                self.scope.add(scaled)
                self.recorder.add_packet(t, msg)
                if self.stim_mode == "calibrate" and self.stim_proc and P.PD_CHANNEL in msg.channels:
                    self.calib.append(scaled[:, msg.channels.index(P.PD_CHANNEL)])
        if changed:
            self.update_buttons()

    def show_status(self, s: P.Status) -> None:
        self.lbl["battery"].setText(f"{s.battery_mv / 1000:.2f} V")
        self.lbl["rate"].setText(f"{s.fs:.2f} SPS")
        self.lbl["samples"].setText(f"{s.sample_count}")
        self.lbl["dropped"].setText(f"{s.dropped}")
        self.lbl["crc"].setText(f"{s.crc_errors}")
        self.lbl["error"].setText(P.ERRORS.get(s.error, str(s.error)) or "none")
        self.vbus.setVisible(s.has(P.STATUS_FLAG_VBUS))
        for i, w in enumerate(self.gain_boxes):
            w.setCurrentIndex(s.gain[i])
        for i, w in enumerate(self.mux_boxes):
            w.setCurrentIndex(s.mux[i])
        idx = self.osr.findData(s.osr_code)
        if idx >= 0:
            self.osr.setCurrentIndex(idx)

    def redraw(self) -> None:
        sc = self.scope
        if not sc.channels or sc.count == 0:
            return
        data = sc.last(DISPLAY_S)
        t = (np.arange(len(data)) - len(data)) / sc.fs
        sos = None
        if self.filt.isChecked() and sc.fs > 100:
            b, a = iirnotch(60, 30, sc.fs)
            sos = np.vstack([butter(2, [1, 45], btype="band", fs=sc.fs, output="sos"), tf2sos(b, a)])
        for i, ch in enumerate(sc.channels):
            if ch not in self.curves:
                continue
            y = data[:, i]
            ok = np.isfinite(y)
            if ch in P.EEG_CHANNELS and sos is not None and ok.sum() > 3 * sc.fs:
                y = y.copy()
                y[ok] = sosfiltfilt(sos, y[ok])
            self.curves[ch].setData(t[ok], y[ok])
        recent = sc.last(4.0)
        for i, ch in enumerate(sc.channels):
            if ch in self.psd_curves:
                y = recent[:, i]
                y = y[np.isfinite(y)]
                if len(y) > sc.fs:
                    f, pxx = welch(y - y.mean(), sc.fs, nperseg=min(len(y), int(2 * sc.fs)))
                    keep = (f > 0.5) & (f < 60)
                    self.psd_curves[ch].setData(f[keep], pxx[keep] + 1e-12)

    def closeEvent(self, e) -> None:
        self.abort_stim()
        if self.recorder.active:
            self.recorder.stop(self.status)
        if self.device and self.device.connected:
            self.send(P.CMD_STOP)
            self.device.disconnect()
        super().closeEvent(e)


def main() -> None:
    app = QApplication([])
    w = MainWindow()
    w.show()
    app.exec()
