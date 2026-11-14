"""Turn a spoken line into a sung one: cut it into syllables, then pitch each syllable to the next note of the
raga's phrase and stretch it to a sung length (ffmpeg rubberband keeps the voice's formants, so it stays the same
singer). Not a neural singer, but it follows the raga's rules instead of reading flat."""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

from . import raga as R

SA_HZ = 146.83  # must equal engine.SA_HZ so voice and drone share one Sa


def _read(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr, ch = w.getframerate(), w.getnchannels()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
    return (a.reshape(-1, ch).mean(1) if ch > 1 else a), sr


def _median_f0(a: np.ndarray, sr: int) -> float:
    n, hop = int(.04 * sr), int(.02 * sr)
    lo, hi = int(sr / 400), int(sr / 70)
    vals = []
    for i in range(0, len(a) - n, hop):
        f = a[i:i + n] - a[i:i + n].mean()
        if np.sqrt((f ** 2).mean()) < 0.02:
            continue
        ac = np.correlate(f, f, "full")[n - 1:]
        if ac[0] <= 0:
            continue
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] / ac[0] > 0.45:
            vals.append(sr / k)
    return float(np.median(vals)) if vals else 190.0


def _cuts(a: np.ndarray, sr: int, k: int) -> list[int]:
    """k-1 cut points near uniform spacing, each moved to the quietest spot within ±80 ms."""
    env = np.convolve(np.abs(a), np.ones(int(.02 * sr)) / int(.02 * sr), mode="same")
    out = []
    for j in range(1, k):
        c, w = int(len(a) * j / k), int(.08 * sr)
        lo = max(out[-1] + int(.05 * sr) if out else 0, c - w)
        out.append(lo + int(np.argmin(env[lo:min(len(a), c + w)])) if lo < min(len(a), c + w) else c)
    return out


def _shift(chunk: np.ndarray, sr: int, ratio: float, tempo: float, tmp: Path) -> np.ndarray:
    src, dst = tmp.with_suffix(".in.wav"), tmp.with_suffix(".out.wav")
    with wave.open(str(src), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes((chunk * 32767).astype("<i2").tobytes())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af",
                    f"rubberband=pitch={ratio:.4f}:tempo={tempo:.4f}:formant=preserved", str(dst)], check=True)
    out, _ = _read(dst)
    return out


def sing_line(src: Path, dst: Path, raga: str, seed: int, line_no: int, beat: float) -> bool:
    """Write the sung version of `src` to `dst`; False if anything fails (caller keeps the spoken line)."""
    try:
        a, sr = _read(src)
        if len(a) < sr // 4:
            return False
        k = max(3, min(24, round(len(a) / sr / 0.26)))
        notes = R.sing_notes(raga, seed + line_no, k, line_no)
        base = _median_f0(a, sr)
        edges = [0] + _cuts(a, sr, k) + [len(a)]
        pieces, tmp = [], dst.with_suffix(".tmp.wav")
        prev = None
        for i in range(k):
            chunk = a[edges[i]:edges[i + 1]]
            if len(chunk) < sr // 40:
                continue
            target = SA_HZ * 2 ** (notes[i] / 12)
            ratio = float(np.clip(target / base, 0.5, 2.0))
            want = beat * (1.6 if i in (k - 1,) else 0.75)  # the last syllable is held
            tempo = float(np.clip(len(chunk) / sr / want, 0.35, 1.6))
            y = _shift(chunk, sr, ratio, tempo, tmp)
            if prev is not None and len(y) and len(prev):  # 25 ms crossfade hides the joins
                f = min(int(.025 * sr), len(y), len(prev))
                ramp = np.linspace(0, 1, f)
                prev[-f:] = prev[-f:] * (1 - ramp) + y[:f] * ramp
                y = y[f:]
            pieces.append(prev) if prev is not None else None
            prev = y
        if prev is not None:
            pieces.append(prev)
        out = np.concatenate(pieces)
        out = out / (np.abs(out).max() or 1) * 0.9
        with wave.open(str(dst), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
            w.writeframes((out * 32767).astype("<i2").tobytes())
        for t in (tmp.with_suffix(".in.wav"), tmp.with_suffix(".out.wav")):
            t.unlink(missing_ok=True)
        return True
    except Exception as e:
        print(f"[sing] fell back to spoken line: {e}")
        return False
