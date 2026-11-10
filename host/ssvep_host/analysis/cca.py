"""Training-free SSVEP classification: CCA against sine/cosine references, and the
filter-bank variant (FBCCA, Chen et al. 2015)."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt


def references(freq: float, fs: float, n: int, harmonics: int = 3) -> np.ndarray:
    t = np.arange(n) / fs
    cols = []
    for h in range(1, harmonics + 1):
        cols += [np.sin(2 * np.pi * h * freq * t), np.cos(2 * np.pi * h * freq * t)]
    return np.stack(cols, axis=1)


def max_canonical_corr(X: np.ndarray, Y: np.ndarray) -> float:
    """X (n, p), Y (n, q): largest canonical correlation."""
    qx, _ = np.linalg.qr(X - X.mean(0))
    qy, _ = np.linalg.qr(Y - Y.mean(0))
    return float(np.linalg.svd(qx.T @ qy, compute_uv=False)[0])


def cca_scores(epoch: np.ndarray, freqs: list[float], fs: float, harmonics: int = 3) -> np.ndarray:
    """epoch (channels, samples) -> one correlation per candidate frequency."""
    n = epoch.shape[1]
    return np.array([max_canonical_corr(epoch.T, references(f, fs, n, harmonics)) for f in freqs])


def filter_bank(fs: float, n_bands: int = 5, low: float = 6.0, step: float = 8.0,
                high: float = 90.0) -> list[np.ndarray]:
    high = min(high, 0.45 * fs)
    return [butter(4, [low + step * m, high], btype="band", fs=fs, output="sos")
            for m in range(n_bands) if low + step * m < high - 2]


def fbcca_scores(epoch: np.ndarray, freqs: list[float], fs: float, harmonics: int = 4,
                 bank: list[np.ndarray] | None = None) -> np.ndarray:
    bank = bank or filter_bank(fs)
    w = np.array([(m + 1) ** -1.25 + 0.25 for m in range(len(bank))])
    rho = np.array([cca_scores(sosfiltfilt(sos, epoch, axis=1), freqs, fs, harmonics) for sos in bank])
    return (w[:, None] * rho**2).sum(0)


def classify(X: np.ndarray, freqs: list[float], fs: float, method: str = "fbcca") -> np.ndarray:
    """X (trials, channels, samples) -> predicted target index per trial."""
    bank = filter_bank(fs) if method == "fbcca" else None
    out = []
    for ep in X:
        s = fbcca_scores(ep, freqs, fs, bank=bank) if method == "fbcca" else cca_scores(ep, freqs, fs)
        out.append(int(np.argmax(s)))
    return np.array(out)
