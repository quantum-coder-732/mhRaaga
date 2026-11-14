"""Offline renderer: turns a music brief into audio with plain numpy.

This is a procedural synthesizer, not a neural text-to-music model. It plays
the brief's raga (or a western scale for pop/lofi/ambient/cinematic) over a
tanpura drone and a taal-driven tabla/kit, with flute, harmonium, sitar or
piano-like lead voices. It runs on any CPU in a few seconds, which keeps the
whole platform usable locally; a neural backend can later replace `render()`
behind the same signature. It does not sing: lyrics are carried as text.
"""
from __future__ import annotations

import hashlib
import random
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 22050
SA_HZ = 146.83  # D3: a common male-voice Sa, keeps the drone warm

# Swaras as semitones above Sa, in ascending order.
RAGA_SCALES = {
    "yaman": [0, 2, 4, 6, 7, 9, 11], "bhairav": [0, 1, 4, 5, 7, 8, 11],
    "bhimpalasi": [0, 2, 3, 5, 7, 9, 10], "darbari": [0, 2, 3, 5, 7, 8, 10],
    "malkauns": [0, 3, 5, 8, 10], "bhupali": [0, 2, 4, 7, 9], "todi": [0, 1, 3, 6, 7, 8, 11],
    "kafi": [0, 2, 3, 5, 7, 9, 10], "desh": [0, 2, 5, 7, 9, 10, 11], "bageshree": [0, 2, 3, 5, 7, 9, 10],
}
# Characteristic phrase (indices into the scale) each raga keeps returning to.
RAGA_PAKAD = {
    "yaman": [6, 1, 2, 3], "bhairav": [0, 1, 2, 1, 0], "malkauns": [0, 1, 2, 3, 2, 1], "bhupali": [0, 1, 2, 1, 0, 4],
}
MAJOR_PENT, MINOR_PENT = [0, 2, 4, 7, 9], [0, 3, 5, 7, 10]

# Taal: beats per cycle and a bol (stroke) per beat. Strokes: D=dha(bass+open) N=na T=tin G=ge .=rest
TAALS = {
    "teental": ("DTTDDTTDNTTNDTTD"), "dadra": "DTNDTN", "keherwa": "DGNTNGTN",
    "rupak": "TTNDTNN", "ektaal": "DDTNTNDDTNTN",
}


def _add(out: np.ndarray, start: int, w: np.ndarray) -> None:
    """out[start:start+len(w)] += w, clipped to the buffer so a long tail never overruns it."""
    w = w[: max(0, len(out) - start)]
    out[start:start + len(w)] += w


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * SR)) / SR


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(t / max(attack, 1e-4), 1.0) * np.exp(-t / max(decay, 1e-3))


def _pluck(freq: float, dur: float, bright: float = 0.6) -> np.ndarray:
    t = _t(dur)
    w = sum((bright ** k) / (k + 1) * np.sin(2 * np.pi * freq * (k + 1) * t) for k in range(8))
    return w * _env(len(t), 0.004, dur / 3.5)


def tanpura(total: float, sa: float = SA_HZ) -> np.ndarray:
    """Pa - Sa' - Sa' - Sa(low) plucks in a slow cycle, strings ringing into each other."""
    out = np.zeros(int(total * SR) + SR * 4)
    cycle = [sa * 1.5, sa * 2, sa * 2, sa]
    step, i = 1.5, 0
    pos = 0.0
    while pos < total:
        w = _pluck(cycle[i % 4], 5.0, bright=0.82)  # jawari: bright upper harmonics
        s = int(pos * SR)
        _add(out, s, w * 0.5)
        pos += step
        i += 1
    return out[: int(total * SR)]


def _tabla_stroke(ch: str) -> np.ndarray:
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(ord(ch))
    if ch == "G":  # bayan open bass, falling pitch
        f = 130 * np.exp(-t * 7) + 70
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.12)
    if ch == "N":  # dayan rim, bright and short
        return (np.sin(2 * np.pi * 420 * t) + .4 * np.sin(2 * np.pi * 840 * t)) * np.exp(-t / 0.05) * .7
    if ch == "T":  # tin, ringing
        return (np.sin(2 * np.pi * 330 * t) + .3 * np.sin(2 * np.pi * 660 * t)) * np.exp(-t / 0.11) * .6
    if ch == "D":  # dha = bass + dayan together
        return _tabla_stroke("G") * .8 + _tabla_stroke("N") * .6
    return rng.standard_normal(n) * 0 * t


def tabla(total: float, bpm: float, taal: str) -> np.ndarray:
    pattern = TAALS.get(taal, TAALS["keherwa"])
    beat = 60.0 / bpm
    out = np.zeros(int(total * SR) + SR)
    i, pos = 0, 0.0
    cache = {c: _tabla_stroke(c) for c in set(pattern)}
    while pos < total:
        ch = pattern[i % len(pattern)]
        w = cache[ch] * (1.0 if i % len(pattern) == 0 else 0.75)
        s = int(pos * SR)
        _add(out, s, w)
        # light filler on the half-beat so slow taals do not feel empty
        if bpm < 90:
            half = cache["N"] * 0.25
            s2 = int((pos + beat / 2) * SR)
            _add(out, s2, half)
        pos += beat
        i += 1
    return out[: int(total * SR)]


def _voice(kind: str, freq_curve: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Render one note whose pitch follows freq_curve (so meend/glides are free)."""
    n = len(freq_curve)
    phase = 2 * np.pi * np.cumsum(freq_curve) / SR
    t = np.arange(n) / SR
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.2 * t) * np.minimum(t / 0.4, 1)
    phase = phase * vib
    if kind == "flute":
        w = np.sin(phase) + .25 * np.sin(2 * phase) + .08 * np.sin(3 * phase)
        w += 0.03 * rng.standard_normal(n)
        env = np.minimum(t / .08, 1) * np.minimum((t[-1] - t + 1e-3) / .12, 1)
    elif kind == "harmonium":
        w = sum(np.sin(phase * k) / k for k in (1, 2, 3, 4, 5, 6, 7)) * .45
        env = np.minimum(t / .03, 1) * np.minimum((t[-1] - t + 1e-3) / .08, 1)
    elif kind == "sitar":
        w = sum((0.7 ** k) * np.sin(phase * (k + 1)) for k in range(9))
        env = np.minimum(t / .003, 1) * np.exp(-t / max(t[-1], 0.1) * 3.2)
    else:  # piano / pad / default: soft pluck
        w = np.sin(phase) + .35 * np.sin(2 * phase) + .12 * np.sin(3 * phase)
        env = np.minimum(t / .006, 1) * np.exp(-t / max(t[-1], 0.1) * 2.6)
    return w * env * 0.5


def _phrase_degrees(scale: list[int], raga: str, bars: int, rng: random.Random) -> list[tuple[int, float]]:
    """(scale degree across 2 octaves, length in beats) following aroha/avaroha with the raga's pakad."""
    seq: list[tuple[int, float]] = []
    pakad = RAGA_PAKAD.get(raga)
    deg = 0
    for bar in range(bars):
        if pakad and bar % 2 == 0:
            for d in pakad:
                seq.append((d, rng.choice([1.0, 1.0, 2.0])))
            deg = pakad[-1]
            continue
        for _ in range(rng.choice([3, 4, 4, 5])):
            deg = max(0, min(len(scale) * 2 - 1, deg + rng.choice([-2, -1, -1, 0, 1, 1, 2])))
            seq.append((deg, rng.choice([0.5, 1.0, 1.0, 1.5, 2.0])))
    seq.append((0, 4.0))  # resolve on Sa
    return seq


def melody(total: float, bpm: float, scale: list[int], raga: str, kind: str, seed: int) -> np.ndarray:
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    out = np.zeros(int(total * SR) + SR * 4)
    pos, prev_f = 0.0, None
    sa = SA_HZ * 2  # lead one octave above the drone
    while pos < total - 2:
        for deg, beats in _phrase_degrees(scale, raga, 4, rng):
            octave, idx = divmod(deg, len(scale))
            f = sa * 2 ** ((scale[idx] + 12 * octave) / 12)
            dur = beats * beat
            n = int(dur * SR)
            curve = np.full(n, f)
            if prev_f and prev_f != f:  # meend: slide into the note over its first ~25%
                g = min(int(n * .25), int(.18 * SR))
                curve[:g] = np.linspace(prev_f, f, g)
            note = _voice(kind, curve, nrng)
            s = int(pos * SR)
            _add(out, s, note)
            prev_f, pos = f, pos + dur
            if pos >= total - 2:
                break
        pos += beat * rng.choice([1, 2])  # breath between phrases
    return out[: int(total * SR)]


def raga_melody(total: float, bpm: float, raga: str, kind: str, seed: int, taal: str, quiet=()) -> np.ndarray:
    """Lead line from raga.form (alap -> gat -> tihai); fades under the sung lines in `quiet` (start, end) seconds."""
    from . import raga as R
    nrng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    out = np.zeros(int(total * SR) + SR * 6)
    prev = None
    for start, semi, dur, sec in R.form(total, raga, seed, beat, len(TAALS.get(taal, TAALS["keherwa"]))):
        if start >= total - 1:
            break
        f = SA_HZ * 2 * 2 ** (semi / 12)
        n = int(min(dur * 1.1, total - start) * SR)
        if n < SR // 20:
            continue
        curve = np.full(n, f)
        if prev and prev != f:  # meend
            g = min(int(n * (.4 if sec == "alap" else .2)), int(.35 * SR))
            curve[:g] = np.linspace(prev, f, g)
        _add(out, int(start * SR), _voice(kind, curve, nrng))
        prev = f
    out = out[: int(total * SR)]
    gain = np.ones(len(out))
    for a, b in quiet:  # leave room for the singer
        i, j = int(max(0, a - .2) * SR), int(min(total, b + .3) * SR)
        gain[i:j] = 0.18
    k = int(.25 * SR)
    gain = np.convolve(gain, np.ones(k) / k, mode="same")
    return out * gain


def pad_chords(total: float, bpm: float, scale: list[int], seed: int) -> np.ndarray:
    """Slow chord bed for non-raga genres: stacked scale thirds, one chord per 4 beats."""
    rng = random.Random(seed)
    beat, out, pos = 60.0 / bpm, np.zeros(int(total * SR) + SR * 4), 0.0
    base = SA_HZ
    while pos < total:
        root = rng.choice([0, 0, 3, 5, 7]) % len(scale)
        dur = 4 * beat
        t = _t(dur + .5)
        chord = np.zeros(len(t))
        for k in (0, 2, 4):
            semi = scale[(root + k) % len(scale)] + 12 * ((root + k) // len(scale))
            f = base * 2 ** (semi / 12)
            chord += np.sin(2 * np.pi * f * t) + .3 * np.sin(2 * np.pi * 2 * f * t)
        chord *= np.minimum(t / .4, 1) * np.minimum((t[-1] - t) / .5, 1) * .18
        s = int(pos * SR)
        _add(out, s, chord)
        pos += dur
    return out[: int(total * SR)]


def kit(total: float, bpm: float) -> np.ndarray:
    """Kick on every other beat, closed hat on the off-beat."""
    beat, out, i, pos = 60.0 / bpm, np.zeros(int(total * SR) + SR), 0, 0.0
    kick = _tabla_stroke("G") * 1.2
    n_h = int(0.05 * SR)
    hat = np.random.default_rng(1).standard_normal(n_h) * np.exp(-np.arange(n_h) / SR / 0.012) * .25
    while pos < total:
        hits = [(beat / 2, hat)] + ([(0.0, kick)] if i % 2 == 0 else [])
        for off, w in hits:
            s = int((pos + off) * SR)
            _add(out, s, w)
        pos += beat
        i += 1
    return out[: int(total * SR)]


def _seed(brief: dict) -> int:
    key = f"{brief.get('title')}|{brief.get('raga')}|{brief.get('genre')}|{brief.get('mood')}|{brief.get('tempo_bpm')}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def render_synth(brief: dict, out_dir: Path, track_id: str, quiet=(), duration_override: float = 0, bed_only: bool = False) -> dict:
    """Render `brief` to out_dir/<track_id>.mp3 (falls back to .wav without ffmpeg).
    Returns {file, duration_seconds, peaks}."""
    duration = duration_override or float(max(20, min(240, brief.get("duration_seconds") or 60)))
    bpm = float(max(50, min(160, brief.get("tempo_bpm") or 84)))
    raga = (brief.get("raga") or "").lower()
    insts = [i.lower() for i in (brief.get("instruments") or [])]
    seed = _seed(brief)

    mix = np.zeros(int(duration * SR))
    if raga in RAGA_SCALES:
        scale = RAGA_SCALES[raga]
        lead = next((i for i in ("flute", "sitar", "harmonium") if i in insts), "flute")
        mix += tanpura(duration) * (1.0 if "tanpura" in insts or not insts else .6)
        from . import raga as R
        taal = brief.get("taal") or "keherwa"
        if raga in R.RAGAS:
            mix += raga_melody(duration, bpm, raga, lead, seed, taal, quiet) * .9
        else:
            mix += melody(duration, bpm, scale, raga, lead, seed) * .9
        if "tabla" in insts or "pakhawaj" in insts or not insts:
            tb = tabla(duration, bpm, taal) * .55
            tb[: int(duration * .18 * SR)] = 0  # alap is free time: drone and lead only
            mix += tb
        if "harmonium" in insts and lead != "harmonium":
            mix += pad_chords(duration, bpm, scale, seed) * .6
    else:
        mood = (brief.get("mood") or "").lower()
        scale = MINOR_PENT if any(w in mood for w in ("sad", "dark", "calm", "meditative", "night")) else MAJOR_PENT
        mix += pad_chords(duration, bpm, scale, seed) * 1.4
        mix += melody(duration, bpm, scale, "", "piano", seed) * .7
        if brief.get("genre") not in ("ambient", "cinematic") or bpm > 100:
            mix += kit(duration, bpm) * .6
        mix += tanpura(duration) * .25 if "tanpura" in insts else 0

    fade = int(2.5 * SR)
    mix[:fade] *= np.linspace(0, 1, fade)
    mix[-fade:] *= np.linspace(1, 0, fade)
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = np.tanh(mix / peak * 1.4) * 0.85  # gentle soft clip = cheap loudness

    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / f"{track_id}.wav"
    with wave.open(str(wav), "wb") as f:
        f.setnchannels(1), f.setsampwidth(2), f.setframerate(SR)
        f.writeframes((mix * 32767).astype("<i2").tobytes())
    final = wav
    try:
        mp3 = out_dir / f"{track_id}.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "128k", str(mp3)], check=True)
        wav.unlink()
        final = mp3
    except (OSError, subprocess.CalledProcessError):
        pass
    chunks = np.array_split(np.abs(mix), 64)
    peaks = [round(float(c.max()), 3) for c in chunks]
    return {"file": final.name, "duration_seconds": int(duration), "peaks": peaks}


# ---- real music: library beds (stored in S3) + Polly vocals, mixed with ffmpeg ----
# Each bed is a real recording; tags say which briefs it suits. Add more files to S3 under library/.
BEDS = [  # built-in default; library/manifest.json (S3, cached in data/library) replaces it once beds are added
    {"key": "library/sitar-tabla-chant-meditation.mp3", "title": "Sitar, Tabla & Chant Meditation",
     "genres": ["raga", "bhajan", "devotional", "classical", "ambient", "folk", "ghazal"], "moods": ["meditative", "calm", "peaceful"], "ragas": []},
]


def _beds() -> list[dict]:
    """The library of real recordings: library/manifest.json from S3 (or the cached copy), else the built-in list."""
    import json
    from . import config, s3
    local = config.LIBRARY_DIR / "manifest.json"
    s3.fetch("library/manifest.json", local) if not local.is_file() else None
    try:
        return json.loads(local.read_text()) or BEDS
    except Exception:
        return BEDS


def _pick_bed(brief: dict):
    """Best-matching recording for the brief: raga match > mood > genre; ties broken by the song's seed so songs vary."""
    g = (brief.get("genre") or "").lower()
    raga = (brief.get("raga") or "").lower()
    if not (raga or g in {"raga", "bhajan", "devotional", "classical", "ambient", "folk", "ghazal", "meditation"}):
        return None
    mood = (brief.get("mood") or "").lower()
    scored = []
    for b in _beds():
        sc = (3 if raga and raga in [r.lower() for r in b.get("ragas", [])] else 0) \
            + (2 if any(m in mood for m in b.get("moods", [])) else 0) + (1 if g in b.get("genres", []) else 0)
        scored.append((sc, b))
    if not scored:
        return None
    top = max(sc for sc, _ in scored)
    pool = [b for sc, b in scored if sc == top]
    return pool[_seed(brief) % len(pool)]


def _peaks(path: Path) -> list[float]:
    raw = subprocess.check_output(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "8000",
                                   "-f", "s16le", "-"])
    a = np.abs(np.frombuffer(raw, dtype="<i2").astype(np.float32)) / 32768
    return [round(float(c.max()), 3) for c in np.array_split(a, 64)] if len(a) else [0.0] * 64


def render(brief: dict, out_dir: Path, track_id: str, token: str = "") -> dict:
    """Real-music path: a library recording as the bed, the lyrics sung-recited over it. Falls back to the
    procedural synth when no bed fits or S3/ffmpeg/Polly are unavailable."""
    from . import config, s3, voice
    bed = _pick_bed(brief)
    local = config.LIBRARY_DIR / Path(bed["key"]).name if bed else None
    if bed and not s3.fetch(bed["key"], local):
        bed = None
    if not bed and not (brief.get("lyrics") or "").strip():
        return render_synth(brief, out_dir, track_id)
    try:
        duration = float(max(20, min(240, brief.get("duration_seconds") or 60)))
        work = out_dir / f".{track_id}"
        bpm = float(max(50, min(160, brief.get("tempo_bpm") or 84)))
        taal = brief.get("taal") or "keherwa"
        beats = len(TAALS.get(taal, TAALS["keherwa"]))
        cycle = beats * 60.0 / bpm
        grid = cycle / 2 if beats >= 12 else cycle
        intro = round(2 * cycle / grid) * grid if grid else 8.0
        intro = max(intro, grid)
        v = voice.synth(brief.get("lyrics") or "", work, token, brief.get("language") or "english", grid=grid, lead=intro,
                        raga=(brief.get("raga") or "").lower() if (brief.get("raga") or "").lower() in __import__("app.raga", fromlist=["x"]).RAGAS else "",
                        beat=60.0 / bpm, seed=_seed(brief))
        if v:
            duration = float(min(240, max(duration, v[1] + intro + 10)))
        total = int(duration)
        matched = bool(bed)  # a real recording always beats the synthesized bed: it sounds like music, not a machine
        out_dir.mkdir(parents=True, exist_ok=True)
        mp3 = out_dir / f"{track_id}.mp3"
        if v and not matched:
            # a recording in another key/tempo fights the singer: build a bed that is in tune and in time with it
            work.mkdir(parents=True, exist_ok=True)
            r = render_synth(brief, work, "bed", quiet=v[3], duration_override=total)
            local = work / r["file"]
            start = 0
        else:
            bed_len = float(subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(local)]).decode())
            start = (_seed(brief) % max(1, int(bed_len - total - 5))) if bed_len > total + 10 else 0
        fo = max(0, total - 4)
        bedf = (f"[0:a]atrim=0:{total},asetpts=N/SR/TB,volume=1.0,"
                f"afade=t=in:d=3,afade=t=out:st={fo}:d=4[bed]")
        args = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-i", str(local)]
        if v:
            args += ["-i", str(v[0])]
            graph = (bedf + f";[1:a]adelay={int(intro*1000)}|{int(intro*1000)},apad=whole_dur={total},aecho=0.8:0.6:70|140:0.25|0.12,"
                     "volume=1.5,asplit[v1][v2];[bed][v1]sidechaincompress=threshold=0.03:ratio=5:attack=30:"
                     "release=600[duck];[duck][v2]amix=inputs=2:normalize=0,loudnorm=I=-15:TP=-1.5:LRA=9[o]")
        else:
            graph = bedf.replace("[bed]", ",loudnorm=I=-15:TP=-1.5[o]")
        subprocess.run(args + ["-filter_complex", graph, "-map", "[o]", "-t", str(total), "-ac", "2",
                               "-ar", "44100", "-b:a", "160k", str(mp3)], check=True, timeout=300)
        peaks = _peaks(mp3)
        s3.upload(mp3, f"tracks/{mp3.name}")
        return {"file": mp3.name, "duration_seconds": total, "peaks": peaks, "polly_chars": v[2] if v else 0, "size_bytes": mp3.stat().st_size}
    except Exception:
        return render_synth(brief, out_dir, track_id)
