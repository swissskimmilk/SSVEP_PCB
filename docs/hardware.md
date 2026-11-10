# Hardware

4-layer board, 97.9 × 46.5 mm.

| Block | Parts |
|---|---|
| MCU / BLE | Seeed XIAO nRF52840 (charger and USB-C on the module) |
| ADC | ADS131M08, 24-bit, 8 channels |
| Front end | 4 × INA333 (gain 501), MCP6002 for the reference and DRL |
| Analog supply | LP5907 3.3 V LDO, switched by the MCU (ANA_EN) |
| Battery | 1S Li-ion on a JST PH, SW101, F101 fuse, Q101 (AO3401A) reverse protection |
| Sync | BPW34 photodiode on a cable to J301, into ADC channel 4 |

## ADC channels

| Channel | Signal | Scale (PGA ×1) |
|---|---|---|
| 0–3 | EEG | 1.2 V / 2²³ / 501 ≈ 0.29 nV per code (±2.4 mV at the electrodes) |
| 4 | Photodiode | 1.2 V / 2²³ |
| 5–7 | Grounded | — |

## XIAO pins

| Pin | Use |
|---|---|
| D3 | ADC CLKIN, 8 MHz from the MCU |
| D4 | ANA_EN |
| D5 | ADC SYNC/RESET |
| D6 | ADC DRDY |
| D7–D10 | SPI: CS, SCLK, MISO, MOSI |

## Jumpers

- **JP1 (CHG_LINK):** bridged lets the XIAO charge the cell; cut to charge it externally.
- **R101 / R102:** select the LDO input. R101 (battery) is fitted; R102 (USB 5 V) is
  for bench use only.
