"""Stimulus session settings. Plain dataclasses so they cross the process boundary as dicts."""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field


@dataclass
class Target:
    freq: float           # Hz
    phase: float = 0.0    # radians, at stimulus onset
    x: float = 0.5        # centre, fraction of screen width
    y: float = 0.5        # centre, fraction of screen height
    size: float = 0.18    # side, fraction of screen height


@dataclass
class StimConfig:
    targets: list[Target] = field(default_factory=list)
    cue_s: float = 1.0
    stim_s: float = 4.0
    rest_s: float = 1.5
    lead_in_s: float = 2.0
    trials_per_target: int = 5
    seed: int | None = None
    screen: int = 0
    patch_corner: str = "bottom-left"  # under the photodiode
    patch_px: int = 60
    onset_marker_frames: int = 3       # patch fully white this many frames at each onset
    layout: str = "corners"            # "corners": spread to the screen edges; "grid": target x/y
    waveform: str = "square"           # "square": full on/off; "sine": smooth, any frequency
    gamma: float = 1.0                 # display gamma; 2.2 makes sine flicker truly sinusoidal
    idle_level: float = 0.5            # target luminance during cue and rest
    windowed: bool = False             # development: small window instead of fullscreen

    def trial_order(self) -> list[int]:
        order = [i for i in range(len(self.targets)) for _ in range(self.trials_per_target)]
        random.Random(self.seed).shuffle(order)
        return order

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StimConfig":
        d = dict(d)
        d["targets"] = [Target(**t) for t in d.get("targets", [])]
        return cls(**d)


# Square-wave friendly at 240 Hz (even frame counts), above alpha, no shared harmonics
# through the 3rd. Start with two; four once two works.
PRESETS = {
    "2 targets (12, 15 Hz)": [12.0, 15.0],
    "4 targets (12, 13.33, 15, 17.14 Hz)": [12.0, 240 / 18, 15.0, 240 / 14],
    "4 classic (8, 10, 12, 15 Hz)": [8.0, 10.0, 12.0, 15.0],
}


def grid_targets(freqs: list[float], phases: list[float] | None = None) -> list[Target]:
    """Lay targets out on a grid away from the corners (the patch lives in one)."""
    n = len(freqs)
    cols = 2 if n <= 4 else 3 if n <= 9 else 4
    rows = (n + cols - 1) // cols
    out = []
    for i, f in enumerate(freqs):
        r, c = divmod(i, cols)
        out.append(Target(freq=f, phase=(phases[i] if phases else 0.0),
                          x=(c + 1) / (cols + 1), y=(r + 1) / (rows + 1),
                          size=min(0.25, 0.7 / max(rows, cols))))
    return out
