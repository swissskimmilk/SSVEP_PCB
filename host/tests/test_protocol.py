import re
import struct
from pathlib import Path

import numpy as np
import pytest

from ssvep_host import protocol as P

PROTOCOL_H = Path(__file__).resolve().parents[2] / "firmware" / "include" / "protocol.h"


@pytest.mark.parametrize("data", [b"", b"\x00", b"\x00\x00", b"abc", b"a\x00b\x00",
                                  bytes(range(256)) * 2, b"\x01" * 254, b"\x01" * 255])
def test_cobs_round_trip(data):
    enc = P.cobs_encode(data)
    assert 0 not in enc
    assert P.cobs_decode(enc) == data


def test_data_packet():
    codes = np.array([[1, -1, 0x7FFFFF, -0x800000, 12345]] * 3, dtype=np.int32)
    body = b"".join(int(v & 0xFFFFFF).to_bytes(3, "big") for v in codes.ravel())
    pkt = struct.pack("<BBBBI", P.PKT_DATA, 3, 0x1F, P.DATA_FLAG_GAP, 1000) + body
    msg = P.parse(pkt)
    assert isinstance(msg, P.DataPacket)
    assert msg.first_index == 1000 and msg.flags == P.DATA_FLAG_GAP
    assert msg.channels == [0, 1, 2, 3, 4]
    np.testing.assert_array_equal(msg.samples, codes)


def test_truncated_packet_rejected():
    assert P.parse(struct.pack("<BBBBI", P.PKT_DATA, 3, 0x1F, 0, 0) + b"\x00" * 10) is None


def test_status_packet():
    raw = struct.pack("<BBBBHHHIIHBB8s8s", P.PKT_STATUS, 1, P.STATUS_FLAG_VBUS, 6, 3870, 0x2802,
                      8000, 500, 2, 1, 0x1F, 0, bytes([0, 1, 2, 3, 0, 0, 0, 0]), bytes(8))
    st = P.parse(raw)
    assert isinstance(st, P.Status)
    assert st.has(P.STATUS_FLAG_VBUS)
    assert st.battery_mv == 3870 and st.gain[3] == 3
    assert st.fs == pytest.approx(8e6 / 2 / 8192)


def test_firmware_constants_match():
    h = PROTOCOL_H.read_text()
    for name in ("PKT_DATA", "PKT_STATUS", "CMD_START", "CMD_STOP", "CMD_SET_OSR", "CMD_SET_GAIN",
                 "CMD_SET_MUX", "CMD_SET_MASK", "CMD_ANALOG_OFF", "CMD_STATUS",
                 "STATUS_FLAG_VBUS", "STATUS_FLAG_STREAMING", "DATA_FLAG_GAP"):
        m = re.search(rf"\b{name}\s*=\s*(0x[0-9A-Fa-f]+|\d+)", h)
        assert m, name
        assert int(m.group(1), 0) == getattr(P, name), name
    # StatusPacket field list, in order, against the Python struct format.
    body = re.search(r"struct __attribute__\(\(packed\)\) StatusPacket \{(.*?)\};", h, re.S).group(1)
    sizes = {"uint8_t": 1, "uint16_t": 2, "uint32_t": 4}
    total = 0
    for typ, arr in re.findall(r"(uint\d+_t)\s+\w+(\[\d+\])?;", body):
        total += sizes[typ] * (int(arr[1:-1]) if arr else 1)
    assert total == struct.calcsize("<BBBBHHHIIHBB8s8s")


def test_uuid_bytes_match():
    h = PROTOCOL_H.read_text()
    m = re.search(r"#define SSVEP_UUID_BYTES\(x\).*?\{(.*?)\}", h, re.S)
    parts = [p.strip() for p in m.group(1).split(",")]
    for x, uuid in [(1, P.SERVICE_UUID), (2, P.DATA_UUID), (3, P.CTRL_UUID), (4, P.STATUS_UUID)]:
        le = bytes(x if p == "(x)" else int(p, 16) for p in parts)
        assert le[::-1].hex() == uuid.replace("-", "")


def test_scale():
    s = P.scale_to_units([0, 4], [0] * 8)
    assert s[0] == pytest.approx(1.2 / 2**23 / 501 * 1e6)
    assert s[1] == pytest.approx(1.2 / 2**23)
