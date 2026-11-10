"""Wire protocol shared with the firmware (firmware/include/protocol.h). Change both together."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

SERVICE_UUID = "a3c40001-5b6e-4f8a-9d2c-7e1f0b5c3a91"
DATA_UUID = "a3c40002-5b6e-4f8a-9d2c-7e1f0b5c3a91"
CTRL_UUID = "a3c40003-5b6e-4f8a-9d2c-7e1f0b5c3a91"
STATUS_UUID = "a3c40004-5b6e-4f8a-9d2c-7e1f0b5c3a91"
DEVICE_NAME = "SSVEP"

PKT_DATA = 0x01
PKT_STATUS = 0x02

DATA_FLAG_CRC_ERROR = 0x01
DATA_FLAG_GAP = 0x02

STATUS_FLAG_ANALOG_ON = 0x01
STATUS_FLAG_STREAMING = 0x02
STATUS_FLAG_VBUS = 0x04
STATUS_FLAG_BLE = 0x08
STATUS_FLAG_USB_CDC = 0x10
STATUS_FLAG_ADC_OK = 0x20

ERRORS = {0: "", 1: "ADC ID mismatch (no ADC answering?)", 2: "ADC register read-back failed",
          3: "bad command"}

CMD_START = 0x01
CMD_STOP = 0x02
CMD_SET_OSR = 0x03
CMD_SET_GAIN = 0x04
CMD_SET_MUX = 0x05
CMD_SET_MASK = 0x06
CMD_ANALOG_OFF = 0x07
CMD_STATUS = 0x08

OSR_VALUES = [128, 256, 512, 1024, 2048, 4096, 8192, 16256]
MUX_NAMES = ["input", "shorted", "+test", "-test"]

N_CHANNELS = 8
EEG_CHANNELS = (0, 1, 2, 3)
PD_CHANNEL = 4
DEFAULT_MASK = 0x1F

ADC_FSR_V = 1.2           # +-1.2 V / PGA gain
INA_GAIN = 1 + 100e3 / 200  # INA333 with RG = R5 + R6 = 200 ohm (partners' sheet): 501

_DATA_HEADER = struct.Struct("<BBBBI")
_STATUS = struct.Struct("<BBBBHHHIIHBB8s8s")


def mask_channels(mask: int) -> list[int]:
    return [ch for ch in range(N_CHANNELS) if mask & (1 << ch)]


def sample_rate(clkin_hz: float, osr_code: int) -> float:
    return clkin_hz / 2 / OSR_VALUES[osr_code]


def volts_per_code(gain_code: int) -> float:
    """ADC input volts per LSB at a PGA gain code (gain = 2**code)."""
    return ADC_FSR_V / (1 << gain_code) / 2**23


def scale_to_units(channels: list[int], gain_codes: list[int]) -> np.ndarray:
    """Per-channel factor: EEG channels to microvolts at the electrodes, the photodiode to volts."""
    out = []
    for ch in channels:
        v = volts_per_code(gain_codes[ch])
        out.append(v / INA_GAIN * 1e6 if ch in EEG_CHANNELS else v)
    return np.array(out)


@dataclass
class DataPacket:
    first_index: int
    ch_mask: int
    flags: int
    samples: np.ndarray  # (n, n_channels) int32 raw ADC codes

    @property
    def channels(self) -> list[int]:
        return mask_channels(self.ch_mask)


@dataclass
class Status:
    fw_version: int
    flags: int
    osr_code: int
    battery_mv: int
    adc_id: int
    clkin_khz: int
    sample_count: int
    dropped: int
    crc_errors: int
    ch_mask: int
    error: int
    gain: list[int] = field(default_factory=lambda: [0] * 8)
    mux: list[int] = field(default_factory=lambda: [0] * 8)

    @property
    def fs(self) -> float:
        return sample_rate(self.clkin_khz * 1e3, self.osr_code)

    def has(self, flag: int) -> bool:
        return bool(self.flags & flag)


def decode_24be(raw: bytes, n_samples: int, n_ch: int) -> np.ndarray:
    b = np.frombuffer(raw, dtype=np.uint8, count=n_samples * n_ch * 3).reshape(n_samples, n_ch, 3)
    v = (b[..., 0].astype(np.int32) << 16) | (b[..., 1].astype(np.int32) << 8) | b[..., 2]
    return np.where(v & 0x800000, v - (1 << 24), v).astype(np.int32)


def parse(pkt: bytes) -> DataPacket | Status | None:
    if not pkt:
        return None
    if pkt[0] == PKT_DATA and len(pkt) >= _DATA_HEADER.size:
        _, n, mask, flags, first = _DATA_HEADER.unpack_from(pkt)
        nch = len(mask_channels(mask))
        if nch == 0 or len(pkt) < _DATA_HEADER.size + n * nch * 3:
            return None
        return DataPacket(first, mask, flags, decode_24be(pkt[_DATA_HEADER.size:], n, nch))
    if pkt[0] == PKT_STATUS and len(pkt) >= _STATUS.size:
        f = _STATUS.unpack_from(pkt)
        return Status(*f[1:12], gain=list(f[12]), mux=list(f[13]))
    return None


def command(op: int, *args: int) -> bytes:
    return bytes([op, *args])


# ---------------------------------------------------------------- COBS (USB framing)

def cobs_encode(data: bytes) -> bytes:
    out = bytearray([0])
    code_at, code = 0, 1
    for b in data:
        if b == 0:
            out[code_at] = code
            code_at, code = len(out), 1
            out.append(0)
        else:
            out.append(b)
            code += 1
            if code == 0xFF:
                out[code_at] = code
                code_at, code = len(out), 1
                out.append(0)
    out[code_at] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes | None:
    out = bytearray()
    i = 0
    while i < len(data):
        code = data[i]
        i += 1
        if code == 0 or i + code - 1 > len(data):
            return None
        out += data[i:i + code - 1]
        i += code - 1
        if code != 0xFF and i < len(data):
            out.append(0)
    return bytes(out)
