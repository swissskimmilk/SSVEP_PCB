# Bring-up

Run these over USB with the analog side powered: a cell or 3.8 V bench supply on J101
with SW101 on, or the 0 Ω moved from R101 to R102. With R101 fitted and only USB
plugged in, the analog 3.3 V rail has no input and the ADC keeps resetting (it answers
`0xFF28` to every frame).

```
cd host
pip install -e .[bench]
python -m ssvep_host.bench selftest   # every input mode on channels 0-4, saves a plot
python -m ssvep_host.bench touch      # touch an electrode input while it records
```

## Expected

| Check | Good result |
|---|---|
| ADC ID | `0x28xx` |
| ±test signal | about ±153–160 mV on every channel |
| Shorted inputs | under 0.3 mV offset, about 3 µV rms |
| Normal mode, no electrodes | each EEG channel near 0 V (outputs centred on vref), noise well above the shorted floor |
| Touch | large 60 Hz on the touched channel |

## Board 1 status

ADC, clock, SPI and firmware pass. The EEG channels all read about +63 mV with almost
no noise, which looks like the INA333 outputs stuck at their low rail. Next: measure
`vref` (U6 pins 5 and 7, R35) — it should be about 1.65 V.

Recordings: [self-test](bench/board1/selftest/selftest.png), [touch](bench/board1/touch/touch.png).
Raw samples are in each folder's `data.npz`; re-plot with `python -m ssvep_host.bench plot <folder>`.
