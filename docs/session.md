# Running a session

1. **Set up.** Tape the photodiode over the sync patch: the bottom-left corner of the
   screen. Put the electrodes over the back of the head (Oz, O1, O2, POz). Unplug USB.
2. **Connect.** In the control window, choose BLE, Scan, then Connect, then Start
   stream. Check the traces look like EEG and the dropped count stays at 0.
3. **Calibrate.** Press Calibrate photodiode. White should read well above black, and
   below 1.1 V.
4. **Run.** Choose a target preset (start with 2 targets) and press Start session.
   Look at the target outlined in red.
5. **Results.** The log shows accuracy when the session ends. To re-run the analysis:

   ```
   python -m ssvep_host.analysis host/sessions/<time>
   ```

## Settings

| Setting | Default | Notes |
|---|---|---|
| Targets | 2 (12, 15 Hz) | Above the alpha band, no shared harmonics |
| Waveform | square | Full on/off. Sine allows any frequency |
| Layout | corners | Targets at the screen edges |
| Cue / stim / rest | 1 / 4 / 1.5 s | Longer stimulation gives higher accuracy |

## How timing works

The photodiode is ADC channel 4, sampled in the same frame as the EEG. The patch is
black between trials, white for the first 3 frames of a trial, and then copies the
target. Each trial onset is therefore an exact sample index, unaffected by BLE or PC
latency. Each frame's brightness is set by when that frame will be on screen, so
skipped frames don't change the frequency.

Each session is saved to `host/sessions/<time>/`: `data.npz` holds the raw samples,
`events.json` the stimulus log.
