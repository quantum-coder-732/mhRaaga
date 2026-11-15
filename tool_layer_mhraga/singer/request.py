"""Build a YuE2 request from an mhRaaga song: style words, tagged lyrics, and the raga melody as the score."""
from __future__ import annotations

import re

from .abc import score_to_abc

TAGS = {"mukhda": "Verse", "antara": "Verse", "verse": "Verse", "chorus": "Chorus", "bridge": "Bridge", "outro": "Outro", "intro": "Intro"}


def tagged_lyrics(lines: list) -> tuple[str, list]:
    """mhRaaga lyric rows [{text, tag}] -> YuE2 text with [Verse]/[Chorus] sections, and the line count of each section."""
    out, counts, cur = [], [], None
    for r in lines:
        if r.get("tag"):
            cur = TAGS.get(r["tag"].lower().split()[0], "Verse"); out.append(("\n\n" if out else "") + f"[{cur}]"); counts.append(0)
        elif r.get("text", "").strip():
            if cur is None:
                cur = "Verse"; out.append("[Verse]"); counts.append(0)
            out.append(r["text"].strip()); counts[-1] += 1
    return "\n".join(out).replace("\n\n\n", "\n\n").replace("]\n\n", "]\n") .replace("\n\n[", "\n\n["), [c for c in counts if c]


def build_request(song: dict, *, style_words: str = "", language: str = "Hindi", voice: str = "deep male lead vocal, soulful and expressive", lyrics_override: str | None = None,
                  rid: str = "song", seed: int = 42, bars_per_line: int = 2) -> dict:
    score = song["score"]
    rows = score["lyrics"]
    if lyrics_override:                                    # same structure, different spelling (for example romanised)
        sung = [x.strip() for x in lyrics_override.strip().splitlines() if x.strip()]
        it = iter(sung); rows = [dict(r) if r.get("tag") else {**r, "text": next(it, r["text"])} for r in rows]
    lyrics, counts = tagged_lyrics(rows)
    n_lines = sum(counts)
    tempo = int(score["meta"]["tempo"])
    style = ", ".join(x for x in [language, style_words.strip(), voice, f"{tempo} BPM"] if x)
    abc = score_to_abc(score, n_lines, bars_per_line, counts, title="")
    return {"id": rid, "style": style, "lyrics": lyrics, "abc": abc, "cot": "melody", "seed": seed, "lines": n_lines, "bars": n_lines * bars_per_line}
