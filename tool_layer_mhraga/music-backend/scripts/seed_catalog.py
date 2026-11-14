"""Register real recordings as catalog tracks: upload to S3 (tracks/) and add them to the store.
Usage: .venv/bin/python -m scripts.seed_catalog   (run from music-backend; needs the service stopped or the same DYNAMO_ENDPOINT)"""
import hashlib, shutil, subprocess
from pathlib import Path

from app import config, engine, s3
from app.main import now, store

DL = Path.home() / "Downloads"
CATALOG = [  # (file, title, genre, language, mood, instrumental)
    ("Sometimes two people.mp3", "Sometimes Two People", "pop", "english", "reflective", False),
    ("What if the one you .mp3", "What If the One You Love", "pop", "english", "heartfelt", False),
    ("When messages disapp.mp3", "When Messages Disappear", "pop", "english", "wistful", False),
    ("boopul-sitar-tabla-amp-chant-meditation-divine-raga-for-spa-538717.mp3", "Sitar, Tabla & Chant Meditation", "bhajan", "sanskrit", "meditative", True),
]
config.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
have = {t["title"] for t in store.all("tracks")}
for fn, title, genre, lang, mood, inst in CATALOG:
    src = DL / fn
    if title in have or not src.is_file():
        continue
    tid = hashlib.sha256(fn.encode()).hexdigest()[:12]
    dest = config.AUDIO_DIR / f"{tid}.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-b:a", "160k", "-ac", "2", str(dest)], check=True)
    dur = int(float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dest)])))
    s3.upload(dest, f"tracks/{dest.name}")
    store.put("tracks", {
        "id": tid, "creator": "raaga", "title": title, "prompt": f"{mood} {genre}", "genre": genre, "language": lang,
        "raga": "", "taal": "", "mood": mood, "tempo_bpm": 90, "instruments": [], "lyrics": "", "brief_source": "catalog",
        "file": dest.name, "duration_seconds": dur, "peaks": engine._peaks(dest), "visibility": "public",
        "plays": 0, "liked_by": [], "created_at": now()})
    print("added", title, dur, "s")
