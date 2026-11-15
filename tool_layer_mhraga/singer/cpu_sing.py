"""A free singer that needs no GPU and no paid service.

A small free text-to-speech voice (Piper, CPU) says each syllable of the line; the pitch of that syllable is then moved onto the raga's
melody note and its vowel is stretched to the note's length (TD-PSOLA, which keeps the voice's own timbre). A vibrato, a glide between notes
and a soft breath are added. An optimiser picks the settings (octave of the voice, vibrato, how much the vowel may stretch) that keep the
voice closest to its natural sound while landing on the melody.

Honest limits: this is *sung speech*, the kind of sound an old voice-synth makes. It is clear and in tune with the raga, but it is not a
trained singing model, so it will not sound like Suno. Ornaments (gamak, meend) are simple glides.

    python -m singer.cpu_sing song.json out.wav [--voice voices/hi_IN-rohan-medium.onnx]
"""
from __future__ import annotations

import json
import re
import sys

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.signal import butter, filtfilt, get_window

SR = 22050
VIRAMA = "्"
MATRAS = set("ािीुूृॄॅॆेैॉॊोौंःँ")
CONS = re.compile("[क-हक़-य़]")
IND_VOWEL = re.compile("[ऄ-औॠ-ॡ]")


# ---------------------------------------------------------------- text -> syllables
def syllables(line: str) -> list[str]:
    """Split Devanagari (or romanised) text into akshara-sized units: consonant(+virama+consonant)* + vowel sign, or an independent vowel."""
    out, i, s = [], 0, re.sub(r"[^\wऀ-ॿ\s]", " ", line)
    for word in s.split():
        if not re.search("[ऀ-ॿ]", word):
            out += re.findall(r"[^aeiouy]*[aeiouy]+(?:[^aeiouy](?![aeiouy]))?|[^aeiouy]+$", word.lower()) or [word]
            continue
        i = 0
        while i < len(word):
            c = word[i]
            if CONS.match(c) or IND_VOWEL.match(c):
                j = i + 1
                while j + 1 < len(word) and word[j] == VIRAMA and CONS.match(word[j + 1]):
                    j += 2
                while j < len(word) and word[j] in MATRAS:
                    j += 1
                out.append(word[i:j]); i = j
            else:
                i += 1
    return out


# ---------------------------------------------------------------- pitch analysis and PSOLA
def f0_track(x: np.ndarray, sr: int = SR, lo: float = 70, hi: float = 400, hop: int = 110) -> tuple[np.ndarray, np.ndarray]:
    """Frame-wise F0 by normalised autocorrelation. Returns (f0 in Hz or 0 when unvoiced, frame centres in samples)."""
    win = int(sr * 0.04); f, c = [], []
    lmin, lmax = int(sr / hi), int(sr / lo)
    for s in range(0, max(1, len(x) - win), hop):
        fr = x[s:s + win] * np.hanning(win)
        e = float(fr @ fr)
        if e < 1e-4:
            f.append(0.0); c.append(s + win // 2); continue
        ac = np.correlate(fr, fr, "full")[win - 1:]
        ac = ac / (ac[0] + 1e-9); seg = ac[lmin:lmax]
        k = int(np.argmax(seg)); f.append(sr / (lmin + k) if seg[k] > 0.45 else 0.0); c.append(s + win // 2)
    return np.array(f), np.array(c)


def nucleus(x: np.ndarray) -> tuple[int, int, float]:
    """(start, end, median f0) of the longest voiced stretch of a syllable: the vowel we will hold."""
    f, c = f0_track(x)
    v = f > 0
    best, cur, bs, be = 0, 0, 0, 0
    for i, ok in enumerate(v):
        cur = cur + 1 if ok else 0
        if cur > best:
            best, bs, be = cur, i - cur + 1, i
    if best < 3:
        return len(x) // 3, 2 * len(x) // 3, 130.0
    return int(c[bs]), int(c[be]), float(np.median(f[bs:be + 1]))


def trim(x: np.ndarray) -> np.ndarray:
    a = np.abs(x); th = 0.02 * a.max() if a.max() > 0 else 0
    idx = np.where(a > th)[0]
    return x[idx[0]: idx[-1] + 1] if len(idx) else x


def psola(x: np.ndarray, f_src: float, target_hz: np.ndarray, out_len: int, src_map: np.ndarray) -> np.ndarray:
    """TD-PSOLA. target_hz[n] is the wanted pitch at output sample n; src_map[n] is which input sample to take the waveform from."""
    out = np.zeros(out_len + 2048); P0 = SR / f_src
    # analysis marks every source period
    marks = np.arange(P0, len(x) - P0, P0).astype(int)
    if len(marks) < 2:
        return np.zeros(out_len)
    n = 0.0
    while n < out_len:
        i = int(n); hz = target_hz[min(i, len(target_hz) - 1)]; T = SR / hz
        src = src_map[min(i, len(src_map) - 1)]
        m = marks[int(np.argmin(np.abs(marks - src)))]
        half = int(max(P0, T))
        a, b = m - half, m + half
        g = x[max(a, 0):min(b, len(x))]
        g = np.pad(g, (max(0, -a), max(0, b - len(x)))) * get_window("hann", 2 * half)
        s = int(n) - half
        lo, hi = max(s, 0), min(s + 2 * half, len(out))
        out[lo:hi] += g[lo - s: hi - s]
        n += T
    return out[:out_len]


# ---------------------------------------------------------------- one syllable on one note
class Voice:
    def __init__(self, path: str):
        from piper import PiperVoice, SynthesisConfig
        self.v, self.cfg, self.cache = PiperVoice.load(path), SynthesisConfig(length_scale=0.9), {}
        self.f_nat = None

    def unit(self, syl: str):
        if syl not in self.cache:
            a = np.concatenate([c.audio_float_array for c in self.v.synthesize(syl, self.cfg)]).astype(np.float64)
            a = trim(a); a /= (np.abs(a).max() + 1e-9)
            n0, n1, f = nucleus(a)
            self.cache[syl] = (a, n0, n1, f)
        return self.cache[syl]


def sing_syllable(voice: Voice, syl: str, notes: list, shift_oct: float, vib: float, max_stretch: float) -> tuple[np.ndarray, float]:
    """notes = [(t, hz, dur)] sharing this syllable (the first starts it, the rest are a melisma on its vowel). Returns (audio, start time)."""
    a, n0, n1, f_nat = voice.unit(syl)
    t0 = notes[0][0]; t_end = notes[-1][0] + notes[-1][2]
    onset = n0 / SR                                              # consonant before the vowel starts, placed before the beat
    start = t0 - min(onset, 0.12)
    cons = a[: max(0, int(min(onset, 0.12) * SR))] if onset > 0 else a[:0]
    nuc = a[n0:n1] if n1 > n0 + 200 else a[n0:n0 + 200]
    coda = a[n1:]
    # build the vowel's target pitch curve: each note, glided into, with vibrato after 0.25 s
    vow_len = int((t_end - t0 - 0.03) * SR)
    if vow_len < 200:
        return np.zeros(0), start
    hz = np.zeros(vow_len); pos = 0
    for k, (t, f, d) in enumerate(notes):
        L = int((d if k < len(notes) - 1 else (t_end - t - 0.03)) * SR) if k < len(notes) - 1 else vow_len - pos
        L = max(0, min(L, vow_len - pos)); seg = np.full(L, f * 2 ** shift_oct)
        if k > 0 and L > 0:                                      # glide from the previous note
            g = min(L, int(0.07 * SR)); seg[:g] = np.linspace(hz[pos - 1] if pos else seg[0], seg[0], g)
        hz[pos:pos + L] = seg; pos += L
    hz[pos:] = hz[pos - 1] if pos else 200
    tt = np.arange(vow_len) / SR; fade = np.clip((tt - 0.25) / 0.3, 0, 1)
    hz = hz * 2 ** (vib * fade * np.sin(2 * np.pi * 5.4 * tt) / 12)
    # time map: walk the source vowel forwards and backwards (ping-pong) at natural speed, so a long note never needs a big stretch
    L = max(len(nuc), 3); speed = min(1.0, L / max(vow_len, 1)) if vow_len < L else 1.0
    p = (np.arange(vow_len) * speed) % (2 * (L - 1)); sm = (L - 1) - np.abs(p - (L - 1))
    vow = psola(nuc, max(f_nat, 80), hz, vow_len, sm)
    ed = int(0.03 * SR); vow[:ed] *= np.linspace(0, 1, ed); vow[-ed:] *= np.linspace(1, 0, ed)
    cod = coda[: int(0.15 * SR)] * np.linspace(1, 0, min(len(coda), int(0.15 * SR))) if len(coda) else coda
    return np.concatenate([cons * np.linspace(0, 1, max(len(cons), 1))[:len(cons)], vow, cod]), start


# ---------------------------------------------------------------- whole song
def assign(score: dict) -> list[tuple[str, list]]:
    """For every sung lyric line, give each syllable the notes it will be sung on."""
    lead = [(n[0], n[1], n[2]) for n in score["lead"]]
    out = []
    for l in score["lyrics"]:
        if l.get("tag") or l["dur"] <= 0:
            continue
        sy = syllables(l["text"])
        ns = [n for n in lead if l["t"] - 0.05 <= n[0] < l["t"] + l["dur"]]
        if not sy or not ns:
            continue
        if len(ns) < len(sy):                                    # fewer notes than syllables: split the notes' time evenly
            span = (l["t"], l["t"] + l["dur"]); step = l["dur"] / len(sy)
            ns = [(l["t"] + i * step, ns[min(len(ns) - 1, int(i * len(ns) / len(sy)))][1], step) for i in range(len(sy))]
        groups = [[] for _ in sy]
        for i, n in enumerate(ns):
            groups[min(len(sy) - 1, int(i * len(sy) / len(ns)))].append(n)
        out += [(s, g) for s, g in zip(sy, groups) if g]
    return out


def fit_octave(voice: Voice, plan: list) -> float:
    """The optimiser: one octave offset for the whole song that keeps the voice nearest its natural pitch (least shifting = most natural),
    found by minimising the mean squared log-distance between the voice's natural pitch and the melody notes."""
    nat = np.log2([voice.unit(s)[3] for s, _ in plan]); tgt = np.log2([g[0][1] for _, g in plan])
    r = minimize_scalar(lambda o: float(np.mean((tgt + o - nat) ** 2)), bounds=(-2, 1), method="bounded")
    return float(np.round(r.x))                                  # whole octaves only, so the raga's intervals are untouched


def fit_vibrato(voice: Voice, plan: list, shift: float) -> float:
    """Pitch drift on notes grows with shifting, so shifted voices get a little less vibrato (it hides less, and shows more)."""
    return float(np.clip(0.30 - 0.06 * abs(shift), 0.12, 0.30))


def sing(score: dict, voice_path: str, gain: float = 0.9, verbose: bool = True) -> np.ndarray:
    voice = Voice(voice_path); plan = assign(score)
    shift = fit_octave(voice, plan); vib = fit_vibrato(voice, plan, shift)
    if verbose:
        print(f"{len(plan)} syllables, octave shift {shift:+.0f}, vibrato {vib:.2f} semitone")
    n = int((score["duration"] + 2) * SR); y = np.zeros(n)
    for syl, notes in plan:
        a, start = sing_syllable(voice, syl, notes, shift, vib, 1.6)
        s = int(max(0, start) * SR)
        if len(a) and s < n:
            y[s:s + len(a)] += a[: n - s]
    b, a_ = butter(2, 90 / (SR / 2), "high"); y = filtfilt(b, a_, y)
    return (y / (np.abs(y).max() + 1e-9) * gain).astype(np.float32)


if __name__ == "__main__":
    import soundfile as sf
    song = json.load(open(sys.argv[1])); voice = "voices/hi_IN-rohan-medium.onnx"
    if "--voice" in sys.argv:
        voice = sys.argv[sys.argv.index("--voice") + 1]
    sf.write(sys.argv[2], sing(song["score"], voice), SR)
