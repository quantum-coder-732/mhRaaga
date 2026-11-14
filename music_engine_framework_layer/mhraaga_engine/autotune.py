"""Auto-tune to the raga's shruti.

Snaps a pitch (Hz) to the nearest allowed svara of a raga in just intonation (the RATIO table in ragas.py), moving it a
fraction `speed` of the way (1.0 = hard snap, like the robotic effect; 0.3 = gentle, keeps the human slide).
Works on single notes, on a pitch track (list of Hz, e.g. from a recorded voice), and on a whole score.
"""
from __future__ import annotations

import math

from .ragas import RATIO


def _cents(a: float, b: float) -> float:
    return 1200.0 * math.log2(a / b)


def allowed_hz(sa: float, scale: set[int], lo_oct: int = -2, hi_oct: int = 2) -> list[float]:
    return sorted(sa * (2.0 ** o) * RATIO[s % 12] for o in range(lo_oct, hi_oct + 1) for s in scale)


def snap(f: float, sa: float, scale: set[int], speed: float = 1.0) -> float:
    """Pull f toward the nearest in-raga pitch by `speed` (0..1) in the log-frequency domain."""
    if f <= 0:
        return f
    cands = allowed_hz(sa, scale)
    target = min(cands, key=lambda c: abs(_cents(f, c)))
    return f * 2.0 ** (_cents(target, f) * max(0.0, min(1.0, speed)) / 1200.0)


def track(hz_track: list[float], sa: float, scale: set[int], speed: float = 0.6, deadband_cents: float = 12.0) -> list[float]:
    """Auto-tune a pitch track (0 = unvoiced). Notes within the dead-band are left alone so vibrato survives."""
    out = []
    cands = allowed_hz(sa, scale)
    for f in hz_track:
        if f <= 0:
            out.append(f)
            continue
        target = min(cands, key=lambda c: abs(_cents(f, c)))
        off = _cents(target, f)
        out.append(f if abs(off) <= deadband_cents else f * 2.0 ** (off * speed / 1200.0))
    return out


def score(events: list[list], sa: float, scale: set[int], speed: float = 0.75) -> tuple[list[list], float]:
    """Snap every lead note of a score. Returns (events, mean absolute correction in cents)."""
    fixed, err = [], []
    for e in events:
        f = snap(e[1], sa, scale, speed)
        err.append(abs(_cents(f, e[1])))
        fixed.append([e[0], round(f, 2), *e[2:]])
    return fixed, (sum(err) / len(err) if err else 0.0)
