# Host

```
pip install -e .[test]
python -m ssvep_host                              # control window
python -m ssvep_host.stim --windowed              # stimulus on its own
python -m ssvep_host.analysis sessions/<time>     # analyse a session
python -m ssvep_host.bench selftest               # ADC check over USB (needs .[bench])
pytest
```

| Module | Job |
|---|---|
| `app.py` | Control window |
| `stim/` | Stimulus window (separate process) |
| `device.py` | BLE, USB serial, simulator |
| `recorder.py` | Saves sessions |
| `analysis/` | Photodiode onsets, epochs, CCA / FBCCA |
| `bench.py` | Bench checks: ADC self-test, touch test, plots |

`INA_GAIN` in `protocol.py` (501) must match the front-end gain resistors.

See [docs/session.md](../docs/session.md).
