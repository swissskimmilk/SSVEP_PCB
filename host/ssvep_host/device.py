"""Links to the board: BLE (bleak), USB serial (bench only), and a simulator.

Every device runs its I/O on a background thread and puts parsed packets
(protocol.DataPacket / protocol.Status) on `self.packets`, which the GUI drains.
"""

from __future__ import annotations

import asyncio
import math
import queue
import threading
import time

import numpy as np

from . import protocol as P


class Device:
    def __init__(self) -> None:
        self.packets: queue.Queue = queue.Queue()
        self.connected = False
        self.error = ""

    def connect(self) -> None:
        raise NotImplementedError

    def disconnect(self) -> None:
        raise NotImplementedError

    def send(self, cmd: bytes) -> None:
        raise NotImplementedError

    def _emit(self, pkt: bytes) -> None:
        msg = P.parse(pkt)
        if msg is not None:
            self.packets.put((time.perf_counter(), msg))


# ---------------------------------------------------------------- BLE

class BleDevice(Device):
    def __init__(self, address: str) -> None:
        super().__init__()
        self.address = address
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._client = None

    @staticmethod
    def scan(timeout: float = 4.0) -> list[tuple[str, str]]:
        from bleak import BleakScanner

        async def run():
            found = await BleakScanner.discover(timeout=timeout, service_uuids=[P.SERVICE_UUID])
            return [(d.name or "?", d.address) for d in found]

        return asyncio.run(run())

    def _run(self, coro, timeout: float = 15.0):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def connect(self) -> None:
        from bleak import BleakClient

        self._thread.start()

        async def go():
            self._client = BleakClient(self.address, disconnected_callback=self._on_disconnect)
            await self._client.connect()
            await self._client.start_notify(P.STATUS_UUID, lambda _, d: self._emit(bytes(d)))
            await self._client.start_notify(P.DATA_UUID, lambda _, d: self._emit(bytes(d)))

        self._run(go())
        self.connected = True

    def _on_disconnect(self, _client) -> None:
        self.connected = False
        self.error = "BLE link lost"

    def disconnect(self) -> None:
        if self._client is not None:
            try:
                self._run(self._client.disconnect(), timeout=5)
            except Exception:
                pass
        self.connected = False
        self._loop.call_soon_threadsafe(self._loop.stop)

    def send(self, cmd: bytes) -> None:
        if self._client is not None and self.connected:
            self._run(self._client.write_gatt_char(P.CTRL_UUID, cmd, response=True))


# ---------------------------------------------------------------- USB serial

class SerialDevice(Device):
    """Bench use only: USB ties the electrodes to the laptop's ground."""

    def __init__(self, port: str) -> None:
        super().__init__()
        self.port = port
        self._ser = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._reader, daemon=True)

    @staticmethod
    def ports() -> list[str]:
        from serial.tools import list_ports
        return [p.device for p in list_ports.comports()]

    def connect(self) -> None:
        import serial
        self._ser = serial.Serial(self.port, 115200, timeout=0.1)
        self._ser.dtr = True  # the firmware only writes once DTR is up
        self.connected = True
        self._thread.start()

    def _reader(self) -> None:
        buf = bytearray()
        while not self._stop.is_set():
            try:
                chunk = self._ser.read(4096)
            except Exception as e:
                self.error = str(e)
                self.connected = False
                return
            buf += chunk
            while (i := buf.find(0)) >= 0:
                frame, buf = bytes(buf[:i]), buf[i + 1:]
                decoded = P.cobs_decode(frame)
                if decoded:
                    self._emit(decoded)

    def disconnect(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(1)
        if self._ser is not None:
            self._ser.close()
        self.connected = False

    def send(self, cmd: bytes) -> None:
        if self._ser is not None:
            self._ser.write(P.cobs_encode(cmd) + b"\x00")


# ---------------------------------------------------------------- simulator

class SimDevice(Device):
    """Fake board for working without hardware.

    EEG is pink-ish noise plus alpha. If `luminance` (a multiprocessing.Value the
    stimulus window writes every frame) is given, the photodiode follows it through
    the board's ~1 ms filter and the EEG gets a small SSVEP from it, so the whole
    record/epoch/classify chain can be exercised at a desk.
    """

    CLKIN_HZ = 8_000_000

    def __init__(self, luminance=None) -> None:
        super().__init__()
        self.luminance = luminance
        self.osr_code = 6
        self.gain = [0] * 8
        self.mux = [0] * 8
        self.mask = P.DEFAULT_MASK
        self.streaming = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._index = 0
        self._rng = np.random.default_rng()

    def connect(self) -> None:
        self.connected = True
        self._thread.start()

    def disconnect(self) -> None:
        self._stop.set()
        self.connected = False

    def send(self, cmd: bytes) -> None:
        op, args = cmd[0], cmd[1:]
        if op == P.CMD_START:
            if not self.streaming:
                self._index = 0
            self.streaming = True
        elif op in (P.CMD_STOP, P.CMD_ANALOG_OFF):
            self.streaming = False
        elif op == P.CMD_SET_OSR:
            self.osr_code = args[0]
        elif op == P.CMD_SET_GAIN:
            self.gain[args[0]] = args[1]
        elif op == P.CMD_SET_MUX:
            self.mux[args[0]] = args[1]
        elif op == P.CMD_SET_MASK:
            self.mask = args[0]
        self._status()

    @property
    def fs(self) -> float:
        return P.sample_rate(self.CLKIN_HZ, self.osr_code)

    def _status(self) -> None:
        st = P.Status(1, (P.STATUS_FLAG_STREAMING if self.streaming else 0) | P.STATUS_FLAG_ADC_OK
                      | P.STATUS_FLAG_ANALOG_ON, self.osr_code, 3900, 0x2802, self.CLKIN_HZ // 1000,
                      self._index, 0, 0, self.mask, 0, list(self.gain), list(self.mux))
        self.packets.put((time.perf_counter(), st))

    def _run(self) -> None:
        t_next_status = 0.0
        t_last = time.perf_counter()
        carry = 0.0
        pd_state = 0.0
        ssvep_state = 0.0
        while not self._stop.is_set():
            time.sleep(0.02)
            now = time.perf_counter()
            if now >= t_next_status:
                t_next_status = now + 1.0
                self._status()
            if not self.streaming:
                t_last = now
                continue
            carry += (now - t_last) * self.fs
            t_last = now
            n = int(carry)
            carry -= n
            if n == 0:
                continue
            lum = float(self.luminance.value) if self.luminance is not None else 0.0
            t = (self._index + np.arange(n)) / self.fs
            uv = np.zeros((n, 8))
            for ch in P.EEG_CHANNELS:
                uv[:, ch] = (self._rng.normal(0, 4, n) + 6 * np.sin(2 * math.pi * 10.2 * t + ch))
            # Board RC on PD_OUT (~1 ms) and a slow, small cortical response to luminance.
            a_pd = math.exp(-1 / (self.fs * 1e-3))
            a_ev = math.exp(-1 / (self.fs * 0.02))
            pd = np.empty(n)
            ev = np.empty(n)
            for i in range(n):
                pd_state = a_pd * pd_state + (1 - a_pd) * lum
                ssvep_state = a_ev * ssvep_state + (1 - a_ev) * (lum - 0.5)
                pd[i], ev[i] = pd_state, ssvep_state
            for ch in P.EEG_CHANNELS:
                uv[:, ch] += 8 * ev * (1.0 if ch >= 2 else 0.5)
            codes = np.zeros((n, 8), dtype=np.int64)
            for ch in range(8):
                vpc = P.volts_per_code(self.gain[ch])
                if self.mux[ch] == 1:
                    volts = self._rng.normal(0, 1e-6, n)
                elif ch in P.EEG_CHANNELS:
                    volts = uv[:, ch] * 1e-6 * P.INA_GAIN
                elif ch == P.PD_CHANNEL:
                    volts = 0.02 + 0.95 * pd + self._rng.normal(0, 1e-4, n)
                else:
                    volts = self._rng.normal(0, 2e-6, n)
                codes[:, ch] = np.clip(np.round(volts / vpc), -2**23, 2**23 - 1)
            chans = P.mask_channels(self.mask)
            pkt = P.DataPacket(self._index, self.mask, 0, codes[:, chans].astype(np.int32))
            self._index += n
            self.packets.put((time.perf_counter(), pkt))
