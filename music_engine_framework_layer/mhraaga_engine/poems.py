"""Spoken-poem bank (poems_bank.json): short rhymed spiritual-love poems per language, used when a song is a poem."""
from __future__ import annotations

import json
import random
from pathlib import Path

_F = Path(__file__).parent / "poems_bank.json"
_BANK = json.loads(_F.read_text()) if _F.exists() else []
_THEME = {"radha": ("krishna", "radha", "flute", "bansuri", "gopi", "कृष्ण", "राधा", "बांसुरी"), "friendship": ("friend", "hold", "hand", "true love", "साथ", "मित्र"),
          "messages": ("message", "text", "chat", "silence", "संदेश"), "patience": ("patien", "wait", "slow", "धीरज", "प्रतीक्षा"),
          "two": ("two people", "sometimes", "meet"), "flute": ("moon", "river", "water", "night")}


def rhyme(lines: list[str]) -> float:
    """Share of couplets whose two lines end in the same last two letters (a cheap, language-neutral rhyme test)."""
    import re
    end = lambda t: re.sub(r"[^\w]", "", t)[-2:]
    pairs = [(lines[i], lines[i + 1]) for i in range(0, len(lines) - 1, 2)]
    return sum(1 for a, b in pairs if end(a) and end(a) == end(b)) / max(1, len(pairs))


def tag(lines: list[str], language: str) -> str:
    v, c = ("Chorus", "Verse") if language == "english" else ("Mukhda", "Antara")
    out = []
    for i in range(0, len(lines), 4):
        out.append(f"[{v if (i // 4) % 2 == 0 else c}]")
        out.extend(lines[i:i + 4])
    return "\n".join(out)


def pick(language: str, hint: str = "", rng: random.Random | None = None) -> tuple[str, str] | None:
    rng = rng or random.Random()
    pool = [p for p in _BANK if p["language"] == language]
    good = [p for p in pool if rhyme(p["lines"]) >= 0.5]
    pool = good or sorted(pool, key=lambda p: -rhyme(p["lines"]))[:2]
    if not pool:
        return None
    low = hint.lower()
    pref = [p for p in pool if any(k in low for k in _THEME.get(p["theme"], ()))]
    p = rng.choice(pref or pool)
    return p["title"], tag(p["lines"], language)
