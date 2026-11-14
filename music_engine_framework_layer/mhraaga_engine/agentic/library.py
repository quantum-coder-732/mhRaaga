"""Reference tunes: analyse real recordings (ffmpeg -> pure-Python Goertzel chroma + energy-envelope tempo) into compact profiles
that the critics compare generated songs against. Profiles are cached in data/library_profiles.json."""
from __future__ import annotations

import json
import math
import struct
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / "data" / "library_profiles.json"
RATE = 8000
EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}


def _pcm(path: Path, start: float, dur: float) -> list[int]:
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", str(path), "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                       capture_output=True, timeout=120)
    n = len(p.stdout) // 2
    return list(struct.unpack(f"<{n}h", p.stdout[: n * 2]))


def _duration(path: Path) -> float:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return 0.0


def _chroma(x: list[int]) -> list[float]:
    out = [0.0] * 12
    n = len(x)
    if n < 2000:
        return out
    win = [0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1)) for i in range(0, n, 1)] if n < 1 else None
    del win
    for midi in range(48, 84):
        f = 440.0 * 2 ** ((midi - 69) / 12)
        w = 2 * math.cos(2 * math.pi * f / RATE)
        s1 = s2 = 0.0
        for v in x:
            s1, s2 = v + w * s1 - s2, s1
        out[midi % 12] += math.sqrt(max(0.0, s1 * s1 + s2 * s2 - w * s1 * s2)) / n
    return out


def _tempo(x: list[int]) -> float:
    hop = RATE // 100
    env = [sum(abs(v) for v in x[i:i + hop]) / hop for i in range(0, len(x) - hop, hop)]
    if len(env) < 400:
        return 0.0
    d = [max(0.0, env[i] - env[i - 1]) for i in range(1, len(env))]
    m = sum(d) / len(d)
    d = [v - m for v in d]
    best, lag_best = -1e18, 0
    for lag in range(30, 121):  # 0.3 .. 1.2 s  -> 200 .. 50 bpm
        r = sum(d[i] * d[i + lag] for i in range(len(d) - lag))
        if r > best:
            best, lag_best = r, lag
    return round(6000.0 / lag_best, 1) if lag_best else 0.0


def analyse(path: Path) -> dict:
    dur = _duration(path)
    chroma = [0.0] * 12
    for frac in (0.2, 0.5, 0.8):
        c = _chroma(_pcm(path, max(0.0, dur * frac - 4), 8))
        chroma = [a + b for a, b in zip(chroma, c)]
    tonic = max(range(12), key=lambda i: chroma[i])
    tot = sum(chroma) or 1.0
    rel = [round(chroma[(tonic + i) % 12] / tot, 4) for i in range(12)]
    tempo = _tempo(_pcm(path, max(0.0, dur * 0.4), 30)) if dur > 20 else 0.0
    return {"file": path.name, "duration": round(dur, 1), "tonic_pc": tonic, "rel_pitch": rel, "tempo": tempo,
            "raga_like": any(k in path.name.lower() for k in ("raga", "sitar", "bansuri", "tanpura", "tabla"))}


def profiles(folder: str | Path, refresh: bool = False) -> list[dict]:
    if CACHE.exists() and not refresh:
        return json.loads(CACHE.read_text())
    folder = Path(folder).expanduser()
    out = []
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() in EXT:
            print("[library] analysing", f.name)
            out.append(analyse(f))
    CACHE.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def cached() -> list[dict]:
    return json.loads(CACHE.read_text()) if CACHE.exists() else []


if __name__ == "__main__":
    import sys
    for p in profiles(sys.argv[1] if len(sys.argv) > 1 else "~/library", refresh=True):
        print(p["file"][:50], "tonic", p["tonic_pc"], "tempo", p["tempo"], [round(v * 100) for v in p["rel_pitch"]])
