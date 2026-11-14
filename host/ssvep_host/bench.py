"""Bench checks over USB serial.

    python -m ssvep_host.bench selftest [--port COM25] [--seconds 6]
    python -m ssvep_host.bench touch    [--port COM25] [--seconds 20]
    python -m ssvep_host.bench plot     FOLDER

selftest records every input mode (normal, shorted, +test, -test) on channels 0-4,
prints mean and noise per channel, and saves data.npz plus selftest.png.
touch records normal mode while you touch an electrode input and prints, per second,
each channel's mean, RMS and 60 Hz amplitude.
Results go to sessions/bench-<time>/.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from . import protocol as P

MODES = {"normal": 0, "shorted": 1, "ptest": 2, "ntest": 3}
CHANNELS = range(5)
NAMES = ["ch 0", "ch 1", "ch 2", "ch 3", "PD"]
UV_PER_CODE = P.ADC_FSR_V / 2**23 * 1e6  # PGA x1, at the ADC input
SETTLE = 100  # samples dropped after each start


class Board:
    def __init__(self, port: str | None) -> None:
        import serial
        from serial.tools import list_ports
        if port is None:
            ports = [p.device for p in list_ports.comports() if p.vid == 0x2886]
            if not ports:
                raise SystemExit("no XIAO found on USB")
            port = ports[0]
        self.port = port
        self.ser = serial.Serial(port, 115200, timeout=0.2)
        self.ser.dtr = True  # the firmware only writes once DTR is up
        time.sleep(0.5)

    def send(self, op: int, *args: int) -> None:
        self.ser.write(P.cobs_encode(P.command(op, *args)) + b"\x00")
        time.sleep(0.05)

    def set_mux(self, mode: int) -> None:
        for ch in CHANNELS:
            self.send(P.CMD_SET_MUX, ch, mode)

    def record(self, seconds: float) -> tuple[np.ndarray, P.Status]:
        self.send(P.CMD_STOP)
        self.ser.reset_input_buffer()
        self.send(P.CMD_START)
        buf = bytearray()
        t0 = time.time()
        while time.time() - t0 < seconds:
            buf += self.ser.read(65536)
        self.send(P.CMD_STOP)
        self.send(P.CMD_STATUS)
        t0 = time.time()
        while time.time() - t0 < 0.5:
            buf += self.ser.read(65536)

        rows, status = [], None
        for frame in bytes(buf).split(b"\x00"):
            pkt = P.parse(P.cobs_decode(frame) or b"") if frame else None
            if isinstance(pkt, P.Status):
                status = pkt
            elif pkt is not None:
                rows.append(pkt.samples)
        if status is None or status.error:
            msg = P.ERRORS.get(status.error, "?") if status else "no status packet"
            raise SystemExit(f"board error: {msg}")
        if not rows:
            raise SystemExit("no data received")
        return np.concatenate(rows), status


def _folder() -> Path:
    f = Path("sessions") / time.strftime("bench-%Y%m%d-%H%M%S")
    f.mkdir(parents=True)
    return f


def selftest(port: str | None, seconds: float) -> Path:
    b = Board(port)
    data, fs = {}, None
    for name, mode in MODES.items():
        b.set_mux(mode)
        x, st = b.record(seconds)
        fs = P.sample_rate(st.clkin_khz * 1e3, st.osr_code)
        data[name] = x[SETTLE:]
        print(f"--- {name}: {len(x)} samples, dropped {st.dropped}, CRC errors {st.crc_errors}")
        v = data[name].astype(float) * UV_PER_CODE
        for ch in CHANNELS:
            print(f"  {NAMES[ch]:<10} mean {v[:, ch].mean() / 1e3:9.3f} mV   "
                  f"rms {v[:, ch].std():8.2f} uV")
    b.set_mux(MODES["normal"])

    folder = _folder()
    np.savez(folder / "data.npz", fs=fs, **data)
    plot(folder)
    return folder


def touch(port: str | None, seconds: float) -> Path:
    b = Board(port)
    b.set_mux(MODES["normal"])
    print(f"recording {seconds:.0f} s: touch an electrode input, hold, then let go")
    x, st = b.record(seconds)
    fs = P.sample_rate(st.clkin_khz * 1e3, st.osr_code)

    n = int(fs)
    t = np.arange(n) / fs
    print("sec | per channel: mean mV, rms uV, 60 Hz amplitude uV")
    for k in range(len(x) // n):
        w = x[k * n:(k + 1) * n].astype(float) * UV_PER_CODE
        w0 = w - w.mean(0)
        a60 = 2 * np.abs((w0 * np.exp(-2j * np.pi * 60 * t)[:, None]).mean(0))
        cols = [f"{w[:, c].mean() / 1e3:7.2f} {w0[:, c].std():8.1f} {a60[c]:8.1f}" for c in CHANNELS]
        print(f"{k:3d} | " + " | ".join(cols))

    folder = _folder()
    np.savez(folder / "data.npz", fs=fs, touch=x)
    plot(folder)
    return folder


def plot(folder: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.signal import welch

    d = np.load(Path(folder) / "data.npz")
    fs = float(d["fs"])
    if "touch" in d:
        return _plot_touch(Path(folder), d["touch"], fs, plt)
    ch = np.arange(5)
    fig, ax = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    fig.suptitle("ADC self-test")

    a = ax[0, 0]
    a.plot(ch, d["ptest"].mean(0) * UV_PER_CODE / 1e3, "o", label="+test")
    a.plot(ch, d["ntest"].mean(0) * UV_PER_CODE / 1e3, "o", label="-test")
    a.axhline(160, color="gray", ls="--", label="nominal")
    a.axhline(-160, color="gray", ls="--")
    a.set_xticks(ch, NAMES)
    a.set_ylabel("mV")
    a.set_title("Test signal")
    a.grid(True)
    a.legend()

    b = ax[0, 1]
    for key, label in (("normal", "normal"), ("shorted", "shorted"), ("ptest", "test")):
        b.plot(ch, d[key].astype(float).std(0) * UV_PER_CODE, "-o", label=label)
    b.set_xticks(ch, NAMES)
    b.set_ylim(0, None)
    b.set_ylabel("µV rms")
    b.set_title("Noise")
    b.grid(True)
    b.legend()

    c = ax[1, 0]
    for key in ("normal", "shorted"):
        x = d[key][:, 0].astype(float) * UV_PER_CODE
        f, p = welch(x - x.mean(), fs=fs, nperseg=min(len(x), 1024))
        c.semilogy(f[1:], np.sqrt(p[1:]), label=key)
    c.set_xlabel("Hz")
    c.set_ylabel("µV/√Hz")
    c.set_title("Spectrum, ch 0")
    c.grid(True)
    c.legend()

    t_ = ax[1, 1]
    n = min(len(d["normal"]), int(2 * fs))
    t = np.arange(n) / fs
    for i in ch:
        x = d["normal"][:n, i].astype(float) * UV_PER_CODE
        t_.plot(t, x - x.mean(), lw=0.8, label=NAMES[i])
    t_.set_xlabel("s")
    t_.set_ylabel("µV")
    t_.set_title("Normal mode")
    t_.grid(True)
    t_.legend()

    out = Path(folder) / "selftest.png"
    fig.savefig(out, dpi=120)
    return out


def _plot_touch(folder: Path, x: np.ndarray, fs: float, plt) -> Path:
    n = int(fs)
    secs = len(x) // n
    t = np.arange(n) / fs
    a60 = np.empty((secs, 5))
    for k in range(secs):
        w = x[k * n:(k + 1) * n].astype(float) * UV_PER_CODE
        w -= w.mean(0)
        a60[k] = 2 * np.abs((w * np.exp(-2j * np.pi * 60 * t)[:, None]).mean(0))

    fig, ax = plt.subplots(2, 1, figsize=(12, 8), constrained_layout=True)
    fig.suptitle("Touch test")
    tt = np.arange(len(x)) / fs
    for c in range(5):
        ax[0].plot(tt, x[:, c] * UV_PER_CODE / 1e3, lw=0.6, label=NAMES[c])
    ax[0].set_xlabel("s")
    ax[0].set_ylabel("mV")
    ax[0].set_title("Raw")
    ax[0].grid(True)
    ax[0].legend()
    for c in range(5):
        ax[1].semilogy(np.arange(secs) + 0.5, a60[:, c], "-o", label=NAMES[c])
    ax[1].set_xlabel("s")
    ax[1].set_ylabel("µV")
    ax[1].set_title("60 Hz amplitude")
    ax[1].grid(True)
    ax[1].legend()

    out = folder / "touch.png"
    fig.savefig(out, dpi=120)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, secs in (("selftest", 6.0), ("touch", 20.0)):
        s = sub.add_parser(name)
        s.add_argument("--port", default=None, help="serial port; default: the first XIAO found")
        s.add_argument("--seconds", type=float, default=secs)
    sub.add_parser("plot").add_argument("folder", type=Path)
    a = ap.parse_args()

    if a.cmd == "selftest":
        print("saved", selftest(a.port, a.seconds))
    elif a.cmd == "touch":
        print("saved", touch(a.port, a.seconds))
    else:
        print("saved", plot(a.folder))


if __name__ == "__main__":
    main()
