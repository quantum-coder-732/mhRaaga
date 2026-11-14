"""Add real recordings (e.g. Pixabay raga/meditation tracks you downloaded) to the mixer's library, one by one.
   .venv/bin/python -m scripts.add_beds ~/Downloads/track1.mp3 ~/Downloads/track2.mp3
   .venv/bin/python -m scripts.add_beds ~/Downloads/pixabay-ragas/      # a whole folder
Each file is uploaded to S3 library/, tagged from its filename (words like calm, devotional, morning, night, yaman,
bhairav ...), and library/manifest.json is updated. Edit the tags afterwards in data/library/manifest.json if needed."""
import json, re, sys
from pathlib import Path

from app import config, s3

RAGAS = ("yaman", "bhairav", "bhimpalasi", "darbari", "malkauns", "bhupali", "todi", "kafi", "desh", "bageshree")
MOODS = ("meditative", "meditation", "calm", "peaceful", "devotional", "joyful", "sad", "romantic", "morning", "night", "evening")
config.LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
man_path = config.LIBRARY_DIR / "manifest.json"
s3.fetch("library/manifest.json", man_path)
man = json.loads(man_path.read_text()) if man_path.is_file() else []
have = {b["key"] for b in man}
files = [f for a in map(Path, sys.argv[1:]) for f in (sorted(a.glob('*.mp3')) if a.is_dir() else [a])]  # a folder adds every mp3 in it
for f in files:
    name = re.sub(r"[^a-z0-9]+", "-", re.sub(r"-\d{5,}$|\(\d+\)", "", f.stem.lower())).strip("-")
    key = f"library/{name}.mp3"
    if key in have or not f.is_file():
        print("skip", f.name); continue
    low = f.stem.lower()
    man.append({"key": key, "title": f.stem, "ragas": [r for r in RAGAS if r in low],
                "moods": [m for m in MOODS if m in low] or ["calm", "meditative"], "genres": ["raga", "bhajan", "devotional", "classical", "ambient"]})
    (config.LIBRARY_DIR / f"{name}.mp3").write_bytes(f.read_bytes())
    print("uploaded" if s3.upload(f, key) else "S3 upload FAILED", key)
man_path.write_text(json.dumps(man, indent=1))
s3.upload(man_path, "library/manifest.json", "application/json")
print(len(man), "beds in the library")
