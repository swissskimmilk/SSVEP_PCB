# SSVEP host

Control window, stimulus window, recording and analysis for the SSVEP board.

```
pip install -e .[test]
python -m ssvep_host          # or: ssvep
python -m ssvep_host.analysis sessions/20261109-160714
pytest
```

Choose **Simulator** as the link to try everything without hardware. The simulated
photodiode follows the stimulus window, so calibration, sessions and classification all
work at a desk.

## Pieces

| Module | Job |
|---|---|
| `app.py` | PyQt6 control window: link, ADC settings, live traces and PSD, photodiode calibration, sessions |
| `stim/window.py` | Fullscreen stimulus in its **own process** (`QOpenGLWindow`, vsync) |
| `device.py` | BLE (bleak), USB serial (bench only), simulator |
| `protocol.py` | Packet format; mirrors `firmware/include/protocol.h` |
| `recorder.py` | `sessions/<time>/data.npz` + `events.json` |
| `analysis/` | Photodiode onsets → trial matching → epochs → CCA / FBCCA |

## Timing

- **Sync patch.** A small square sits in a screen corner under the photodiode.
  - It's black between trials and white for the first 3 frames of each trial.
  - During a trial it mirrors the cued target.
- **Onsets.** The photodiode is ADC channel 4, sampled in the same frame as the EEG, so
  each onset is an exact sample index. Neither the host clock nor BLE latency enters
  the timing.
  - The host clock is used only to work out which logged trial each onset belongs to.
- **Frequency check.** Each trial's photodiode frequency is compared with the log.
- **Stimulus frames.** Each frame's luminance depends on the vsync it will appear on,
  not on how many frames were painted.
  - On Windows, about 20% of frames stall for ~16 ms (measured on this laptop's 240 Hz
    panel). A stall holds one image longer, but frequency and phase stay exact.
  - Missed vsyncs are reported for each trial.
  - For the cleanest stimulus, set the display to 60 or 120 Hz, or use a dedicated
    monitor.

`INA_GAIN` in `protocol.py` (501) assumes the partners' RG = R5 + R6 = 200 Ω. Update it
if they change the gain resistors.
