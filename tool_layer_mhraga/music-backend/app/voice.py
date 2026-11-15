"""Vocal layer, no AWS Polly.
  English lines    -> Kalkee's text-to-speech (POST /api/chat/tts, Piper/Azure) with the caller's Kalkee token.
  Devanagari lines -> open-source Piper voices run inside this app (free, offline): Hindi -> hi_IN priyamvada,
                      Marathi and Sanskrit -> mr_IN google (Marathi shares Devanagari/phonetics with Sanskrit).
Licences: mr_IN google = CC BY-SA 4.0 (credit "Google / Piper voices"); hi_IN priyamvada = CC BY-NC-SA 4.0 (NON-COMMERCIAL;
switch it off with MUSIC_HINDI_VOICE=0). Models are fetched once into data/voices (from S3 voice-models/ if present, else
Hugging Face rhasspy/piper-voices)."""
from __future__ import annotations

import math
import os
import re
import subprocess
from pathlib import Path

import httpx

from . import config

_SECTION = re.compile(r"^\s*[\[(].*?[\])]\s*$")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
VOICE_ID = "en-IN-NeerjaNeural"  # Indian-English female (Piper 'slp' unless Azure is keyed)


HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
MODELS = {"hindi": ("hi_IN-priyamvada-medium", "hi/hi_IN/priyamvada/medium"),
          "marathi": ("mr_IN-google-medium", "mr/mr_IN/google/medium")}
_loaded: dict = {}


def lines_of(lyrics: str, limit: int = 30) -> list[str]:
    return [l.strip() for l in (lyrics or "").splitlines() if l.strip() and not _SECTION.match(l)][:limit]


def _model(kind: str):
    """Load (and download once) a local Piper voice. None if unavailable."""
    from . import s3
    if kind in _loaded:
        return _loaded[kind]
    name, path = MODELS[kind]
    d = config.DATA_DIR / "voices"
    d.mkdir(parents=True, exist_ok=True)
    try:
        for ext in ("onnx", "onnx.json"):
            f = d / f"{name}.{ext}"
            if not (f.is_file() and f.stat().st_size) and not s3.fetch(f"voice-models/{name}.{ext}", f):
                r = httpx.get(f"{HF}/{path}/{name}.{ext}", timeout=300, follow_redirects=True)
                r.raise_for_status()
                f.write_bytes(r.content)
        from piper import PiperVoice
        _loaded[kind] = PiperVoice.load(str(d / f"{name}.onnx"))
    except Exception as e:
        print(f"[voice] local {kind} voice unavailable: {e}")
        _loaded[kind] = None
    return _loaded[kind]


def _local(text: str, kind: str, out: Path) -> bool:
    import wave
    v = _model(kind)
    if not v:
        return False
    with wave.open(str(out), "wb") as w:
        v.synthesize_wav(text, w)
    return True


def synth(lyrics: str, work: Path, token: str = "", language: str = "english", grid: float = 0, lead: float = 0, raga: str = "", beat: float = 0.7, seed: int = 0) -> tuple[Path, float, int, list] | None:
    """Return (wav, seconds, characters) of the English lines read slowly with pauses, or None."""
    ls = lines_of(lyrics)
    token = token or config.AKANADE_TOKEN
    if not ls or not config.VOICE_ENABLED:
        return None
    local_kind = "hindi" if language == "hindi" and os.getenv("MUSIC_HINDI_VOICE", "1") == "1" else "marathi"
    try:
        work.mkdir(parents=True, exist_ok=True)
        parts = []
        for i, line in enumerate(ls):
            p = work / f"line{i}.wav"
            if _DEVANAGARI.search(line):
                if not _local(line, local_kind, p):
                    continue
            elif token:
                r = httpx.post(f"{config.AKANADE_URL}/api/chat/tts", timeout=60, headers={"Authorization": f"Bearer {token}"},
                               json={"text": line, "voice_id": VOICE_ID, "rate": 0.85})
                r.raise_for_status()
                p.write_bytes(r.content)
            else:
                continue
            if raga and os.getenv("MUSIC_SING", "0") == "1":
                from . import sing
                sp = work / f"sung{i}.wav"
                if sing.sing_line(p, sp, raga, seed, i, beat):
                    p = sp
            parts.append(p)
        if not parts:
            return None
        ls = [l for l in ls][:len(parts)] if len(parts) == len(ls) else ls
        args = ["ffmpeg", "-y", "-loglevel", "error"]
        for p in parts:
            args += ["-i", str(p)]
        def _dur(f):
            return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]).decode())
        durs = [_dur(p) for p in parts]
        # snap every line to the taal grid so each begins on a beat-aligned bar and the music breathes between lines
        pads = [(math.ceil((d + 0.8) / grid) * grid - d) if grid else 1.6 for d in durs]
        windows, t = [], lead
        for d, pd in zip(durs, pads):
            windows.append((t, t + d))
            t += d + pd
        chain = "".join(f"[{i}:a]apad=pad_dur={pads[i]:.3f}[a{i}];" for i in range(len(parts)))
        chain += "".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[o]"
        out = work / "voice.wav"
        subprocess.run(args + ["-filter_complex", chain, "-map", "[o]", "-ar", "44100", "-ac", "1", str(out)], check=True)
        dur = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)]).decode())
        return out, dur, sum(len(l) for l in ls), windows
    except Exception as e:
        print(f"[voice] Kalkee TTS unavailable: {e}")
        return None
