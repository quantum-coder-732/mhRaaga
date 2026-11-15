"""Style tags -> musical choices, the way Suno's "Styles" box works: free words like "sufi qawwali, harmonium, dholak, handclaps, building crescendo".

parse(text) reads the words it knows and returns hints the composer and the synth act on:
  lead      bansuri | harmonium | veena       the lead instrument
  tala      a tala from tala.py               the rhythm cycle
  tempo     beats per minute
  ensemble  extra players the synth adds: dholak (a low two-headed drum), clap (hand claps), manjira (brass cymbals)
  ragas     raga names that suit the style (the composer picks from these when no raga is chosen)
  tags      the recognised words (shown on the song)
Words it does not know are kept in the style text and sent to the language model as a mood hint, so nothing typed is ignored.
Explicit choices on the Create page always win over these hints. Honest limit: these are a fixed table of rules, not a model that has heard the genre."""
from __future__ import annotations

import re

# word -> hints. Earlier entries win for lead/tala/tempo; ensemble and ragas are merged.
TABLE = {
    "qawwali": dict(lead="harmonium", tala="dadra", tempo=96, ensemble=["dholak", "clap"], ragas=["Bhairavi", "Kafi", "Yaman"]),
    "sufi": dict(lead="harmonium", tala="keherwa", tempo=88, ensemble=["dholak", "clap"], ragas=["Bhairavi", "Kafi", "Bhoopali"]),
    "bollywood": dict(lead="bansuri", tala="keherwa", tempo=108, ensemble=["dholak"], ragas=["Yaman", "Kafi", "Bhoopali"]),
    "film": dict(lead="bansuri", tala="keherwa", tempo=100, ensemble=["dholak"], ragas=["Yaman", "Kafi"]),
    "ghazal": dict(lead="harmonium", tala="dadra", tempo=70, ensemble=[], ragas=["Bhairavi", "Yaman", "Kafi"]),
    "bhajan": dict(lead="harmonium", tala="keherwa", tempo=78, ensemble=["dholak", "manjira"], ragas=["Bhairavi", "Yaman", "Bhoopali"]),
    "kirtan": dict(lead="harmonium", tala="keherwa", tempo=96, ensemble=["dholak", "manjira", "clap"], ragas=["Bhairavi", "Kafi"]),
    "devotional": dict(lead="harmonium", tala="keherwa", tempo=76, ensemble=["manjira"], ragas=["Bhairavi", "Yaman"]),
    "folk": dict(lead="bansuri", tala="dadra", tempo=100, ensemble=["dholak", "clap"], ragas=["Kafi", "Bhoopali"]),
    "classical": dict(lead="bansuri", tala="teental", tempo=64, ensemble=[], ragas=["Yaman", "Bhairavi"]),
    "meditative": dict(lead="bansuri", tala="keherwa", tempo=56, ensemble=[], ragas=["Bhoopali", "Yaman"]),
    "lullaby": dict(lead="bansuri", tala="dadra", tempo=58, ensemble=[], ragas=["Bhoopali"]),
    "cinematic": dict(lead="bansuri", tala="keherwa", tempo=84, ensemble=["dholak"], ragas=["Yaman"]),
    "romantic": dict(lead="bansuri", tala="dadra", tempo=82, ensemble=[], ragas=["Yaman", "Kafi"]),
}
LEADS = {"harmonium": "harmonium", "bansuri": "bansuri", "flute": "bansuri", "veena": "veena", "sitar": "veena"}
ENSEMBLE = {"dholak": "dholak", "dholki": "dholak", "clap": "clap", "claps": "clap", "handclaps": "clap", "handclap": "clap", "clapping": "clap", "manjira": "manjira", "cymbals": "manjira", "jhanjh": "manjira"}
TEMPO = {"slow": -14, "gentle": -8, "fast": 18, "upbeat": 14, "energetic": 16, "building": 0, "crescendo": 0}


def parse(text: str) -> dict:
    words = [w for w in re.split(r"[,;/|\n]+|\s+(?:and|with|\+)\s+", (text or "").lower()) if w.strip()]
    flat = re.findall(r"[a-z]+", (text or "").lower())
    out = {"lead": "", "tala": "", "tempo": 0, "ensemble": [], "ragas": [], "tags": []}
    present = set(flat)
    for w, t in TABLE.items():                       # table order is priority: qawwali beats sufi, which beats devotional
        if w in present:
            out["tags"].append(w)
            out["lead"] = out["lead"] or t["lead"]
            out["tala"] = out["tala"] or t["tala"]
            out["tempo"] = out["tempo"] or t["tempo"]
            out["ensemble"] += [e for e in t["ensemble"] if e not in out["ensemble"]]
            out["ragas"] += [r for r in t["ragas"] if r not in out["ragas"]]
    for w in flat:
        if w in LEADS:
            out["lead"] = LEADS[w]; out["tags"].append(w)               # a named instrument beats the genre's default
        if w in ENSEMBLE:
            if ENSEMBLE[w] not in out["ensemble"]:
                out["ensemble"].append(ENSEMBLE[w])
            out["tags"].append(w)
    if out["tempo"]:
        out["tempo"] = max(40, min(180, out["tempo"] + sum(TEMPO[w] for w in flat if w in TEMPO)))
    elif any(w in TEMPO for w in flat):
        out["tempo"] = max(40, min(180, 80 + sum(TEMPO[w] for w in flat if w in TEMPO)))
    return out
