"""Session recording: raw ADC codes with their sample index, plus the stimulus log.

Layout of a session folder:
    data.npz     index (int64), raw (int32, n x ch), channels, gain_codes, fs, scale,
                 packet_index / packet_time (host perf_counter when each packet arrived)
    events.json  stimulus log from the stimulus window, settings, notes
Sample index is the authority for timing; host times are only a fallback.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

import numpy as np

from . import protocol as P


class Recorder:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.folder: Path | None = None
        self._chunks: list[np.ndarray] = []
        self._index: list[np.ndarray] = []
        self._pkt_index: list[int] = []
        self._pkt_time: list[float] = []
        self.events: list[dict] = []
        self.meta: dict = {}
        self.channels: list[int] | None = None

    @property
    def active(self) -> bool:
        return self.folder is not None

    @property
    def n_samples(self) -> int:
        return sum(len(c) for c in self._chunks)

    def start(self, meta: dict) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.folder = self.root / stamp
        self.folder.mkdir(parents=True, exist_ok=True)
        self._chunks, self._index, self._pkt_index, self._pkt_time = [], [], [], []
        self.events = []
        self.channels = None
        self.meta = dict(meta, started=stamp)
        return self.folder

    def add_packet(self, t_host: float, pkt: P.DataPacket) -> None:
        if not self.active:
            return
        if self.channels is None:
            self.channels = pkt.channels
        elif pkt.channels != self.channels:
            return  # channel set changed mid-session; settings are locked while recording
        self._chunks.append(pkt.samples)
        self._index.append(pkt.first_index + np.arange(len(pkt.samples), dtype=np.int64))
        self._pkt_index.append(pkt.first_index)
        self._pkt_time.append(t_host)

    def add_event(self, event: dict) -> None:
        if self.active:
            self.events.append(event)

    def stop(self, status: P.Status | None) -> Path | None:
        if not self.active:
            return None
        folder = self.folder
        channels = self.channels or []
        raw = np.concatenate(self._chunks) if self._chunks else np.zeros((0, len(channels)), np.int32)
        index = np.concatenate(self._index) if self._index else np.zeros(0, np.int64)
        gains = status.gain if status else [0] * 8
        fs = status.fs if status else float("nan")
        np.savez_compressed(
            folder / "data.npz",
            index=index, raw=raw, channels=np.array(channels), gain_codes=np.array(gains),
            fs=fs, scale=P.scale_to_units(channels, gains),
            packet_index=np.array(self._pkt_index, np.int64),
            packet_time=np.array(self._pkt_time),
        )
        meta = dict(self.meta, status=asdict(status) if is_dataclass(status) else None,
                    ina_gain=P.INA_GAIN, pd_channel=P.PD_CHANNEL, eeg_channels=list(P.EEG_CHANNELS))
        (folder / "events.json").write_text(json.dumps({"meta": meta, "events": self.events}, indent=1))
        self.folder = None
        return folder


def load(folder: Path) -> tuple[dict, dict]:
    """Return (arrays, events_json). arrays['data'] is scaled: uV for EEG, V for the photodiode."""
    folder = Path(folder)
    z = np.load(folder / "data.npz")
    arrays = {k: z[k] for k in z.files}
    arrays["data"] = arrays["raw"] * arrays["scale"]
    return arrays, json.loads((folder / "events.json").read_text())
