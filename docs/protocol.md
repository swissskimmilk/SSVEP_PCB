# Protocol

Defined in `firmware/include/protocol.h` and mirrored in `host/ssvep_host/protocol.py`.
A test checks the two match.

## BLE

| Characteristic | UUID | Use |
|---|---|---|
| Service | `a3c40001-5b6e-4f8a-9d2c-7e1f0b5c3a91` | |
| Data | `…0002…` | Notify: data packets |
| Control | `…0003…` | Write: commands |
| Status | `…0004…` | Read / notify: status packet, 1 Hz |

Advertised name: `SSVEP`. Over USB serial the same packets are COBS-framed and end in
`0x00`.

## Data packet

```
u8 type=0x01 | u8 n_samples | u8 ch_mask | u8 flags | u32 first_index | samples
```

Samples are 24-bit big-endian two's complement, one per enabled channel. `first_index`
counts every ADC sample since Start, so gaps are visible. Flags: `0x01` CRC error,
`0x02` samples lost before this packet.

## Commands

| Byte | Command | Arguments |
|---|---|---|
| `0x01` | Start | |
| `0x02` | Stop | |
| `0x03` | Set OSR | code (6 = 488 SPS, 5 = 977 SPS) |
| `0x04` | Set gain | channel, code (gain = 2^code) |
| `0x05` | Set input | channel, 0 normal, 1 shorted, 2 / 3 test signal |
| `0x06` | Set channel mask | mask |
| `0x07` | Analog off | |
| `0x08` | Request status | |

The status packet carries the battery voltage, sample and drop counts, CRC errors,
gains, inputs, and a USB-power flag.
