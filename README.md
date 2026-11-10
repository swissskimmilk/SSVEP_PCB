# SSVEP EEG board

Four-channel EEG front end (partners' INA333 + ADS131M08 design) with a Seeed XIAO
nRF52840 for BLE, a 1S Li-ion supply, and a screen-sync photodiode on ADC channel 4.

| Folder | Contents |
|---|---|
| `SSVEP_PCB/` | KiCad project: schematic sheets and the 4-layer board |
| `design/` | Circuit JSON, part records, BOM/order files, generator scripts |
| `fab/` | JLCPCB Gerbers |
| `libs/`, `ul_*` | Symbol and footprint libraries |
| `firmware/` | XIAO firmware (PlatformIO); see its README |
| `host/` | PyQt6 control and stimulus windows, recording, analysis; see its README |
