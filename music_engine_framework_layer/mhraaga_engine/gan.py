"""Phrase GAN: a small generative adversarial network that invents melodic phrases for Kalkee's producer agents.

Generator G: noise(6) -> 16 -> 8 melodic contour values.  Discriminator D: contour(8) -> 16 -> realness score.
Trained offline (mhraaga_engine/agentic/train_gan.py, numpy) on 8-note phrases harvested from the raga grammar across
every classical raga; the trained weights ship in gan_weights.json. Inference here is plain Python, no numpy, so it runs
in the Lambda as is.

At composition time a generated contour is snapped to the raga's own notes (so it can never leave the raga), and D's score
is kept as a critic signal: a phrase D finds unreal is not used.
This is a tiny model trained on grammar output, so it varies phrases in the grammar's style; it does not learn taste.
"""
from __future__ import annotations

import json
import math
import os
import random

_W = None
ZD = 6


def _load():
    global _W
    if _W is None:
        p = os.path.join(os.path.dirname(__file__), "gan_weights.json")
        _W = json.load(open(p)) if os.path.exists(p) else {}
    return _W


def available() -> bool:
    return bool(_load())


def _dense(x, W, b, act):
    out = []
    for j in range(len(b)):
        s = b[j] + sum(x[i] * W[i][j] for i in range(len(x)))
        out.append(act(s))
    return out


def _lrelu(v): return v if v > 0 else 0.2 * v
def _sig(v): return 1 / (1 + math.exp(-max(-30, min(30, v))))


def discriminate(contour: list[float]) -> float:
    """0..1, how much the phrase looks like the training phrases. Contour values are (semitone - 6) / 12 from Sa."""
    w = _load()
    if not w:
        return 0.5
    h = _dense(contour, w["D1"], w["d1"], _lrelu)
    return _dense(h, w["D2"], w["d2"], _sig)[0]


def generate(rng: random.Random, scale: list[int], tries: int = 6, floor: float = 0.35) -> tuple[list[int], float] | None:
    """Return (8 semitone values inside the raga, D score) or None if no weights or nothing passed the critic."""
    w = _load()
    if not w or not scale:
        return None
    pool = sorted({s + 12 * o for s in scale for o in (0, 1)} | {12})
    best = None
    for _ in range(tries):
        z = [rng.gauss(0, 1) for _ in range(ZD)]
        h = _dense(z, w["G1"], w["g1"], math.tanh)
        c = _dense(h, w["G2"], w["g2"], math.tanh)
        notes = [min(pool, key=lambda p: abs(p - (v * 12 + 6))) for v in c]       # snap to the raga
        notes = [n for i, n in enumerate(notes) if i == 0 or n != notes[i - 1]] or [0]
        if len(notes) < 4:
            continue
        sc = discriminate([(n - 6) / 12 for n in (notes + [notes[-1]] * 8)[:8]])
        if best is None or sc > best[1]:
            best = (notes, sc)
        if sc >= floor:
            break
    return best if best and best[1] >= floor else None
