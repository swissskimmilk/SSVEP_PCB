# SSVEP EEG board

A 4-channel EEG board that streams over BLE, with a photodiode that marks screen flashes
in the same samples as the EEG.

```
host/      PyQt6 control + stimulus windows, recording, analysis
firmware/  XIAO nRF52840 firmware (PlatformIO)
SSVEP_PCB/ KiCad project
design/    circuit JSON, BOM, scripts
fab/       Gerbers
```

## Quick start

```
cd host && pip install -e . && python -m ssvep_host    # pick "Simulator" to try it
cd firmware && pio run -t upload                        # flash the board over USB
```

## Docs

- [Running a session](docs/session.md)
- [Hardware](docs/hardware.md)
- [Protocol](docs/protocol.md)
- [Bring-up](docs/bringup.md)

> Never put electrodes on a person while USB is plugged in. Battery and BLE only.
