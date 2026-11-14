"""Offline poem factory: asks the language model for short rhymed spiritual-love poems (the style of the reference tunes: plain words, couplets,
Radha-Krishna imagery) in each language and stores them in data/poems.json. Run once, then poems are used without any network.
usage: OPENROUTER_API_KEY=... python3 -m mhraaga_engine.agentic.make_poems [per_theme]"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "data" / "poems.json"
LANGS = ("english", "hindi", "marathi", "telugu", "gujarati", "kannada", "tamil")
THEMES = {
    "radha": "Radha and Krishna: when He played the flute, she listened; love that needs no words",
    "friendship": "true love is friendship: holding hands, patience, loving from within, not energy or perfect days",
    "messages": "modern longing: messages that disappear, two people who understand each other in silence",
    "patience": "patience in love: waiting without demanding, love that grows slowly like dawn",
    "two": "sometimes two people meet and everything quiet becomes music",
    "flute": "the sound of the flute at the river, the moon on the water, a heart made of light",
}
STYLE = ("Plain, intimate, rhymed couplets. Short lines of 4 to 9 words. Gentle imagery (flute, moon, river, hands, silence). No clichés piled up, "
         "no preaching. Example of the voice: 'When He played, she listened.' / 'So hold each other's hands, hold tight and true.'")


def ask(lang: str, theme: str, key: str, model: str = "z-ai/glm-5.3-flash") -> dict:
    sysmsg = (f"You write spoken poems for music. Reply with ONE JSON object: {{\"title\": str (max 6 words), \"lines\": [14 to 18 strings]}}. "
              f"Write in {lang}, in its native script. Rhyme every pair of lines (aabb): the two lines of each couplet MUST END with the same sound, ideally the same final syllable or word ending, in {lang}. Check each couplet before answering. {STYLE}")
    body = {"model": model, "temperature": 0.9, "max_tokens": 4000, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": sysmsg}, {"role": "user", "content": f"Theme: {THEMES[theme]}"}]}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "mhRaaga"})
    with urllib.request.urlopen(req, timeout=60) as r:
        t = json.load(r)["choices"][0]["message"]["content"]
    d = json.loads(t[t.index("{"): t.rindex("}") + 1])
    d["lines"] = [re.sub(r"\s+", " ", str(x)).strip() for x in d["lines"] if str(x).strip()]
    return {"title": str(d["title"])[:60], "lines": d["lines"], "theme": theme, "language": lang}


def main(per_theme: int = 1) -> None:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        sys.exit("set OPENROUTER_API_KEY")
    from ..poems import rhyme
    bank = [p for p in (json.loads(OUT.read_text()) if OUT.exists() else []) if rhyme(p["lines"]) >= 0.5]
    for lang in LANGS:
        for theme in THEMES:
            have = sum(1 for p in bank if p["language"] == lang and p["theme"] == theme)
            for _ in range(max(0, per_theme - have) * 4):
                if sum(1 for p in bank if p["language"] == lang and p["theme"] == theme) >= per_theme:
                    break
                try:
                    p = None
                    for model in ("z-ai/glm-5.3-flash", "deepseek/deepseek-v4-flash", "z-ai/glm-5.3-flash"):
                        try:
                            p = ask(lang, theme, key, model)
                            break
                        except Exception:
                            continue
                    if p is None:
                        raise RuntimeError("no model answered")
                    if 10 <= len(p["lines"]) <= 24 and rhyme(p["lines"]) >= 0.5:
                        bank.append(p)
                        print(lang, theme, p["title"], len(p["lines"]))
                except Exception as e:
                    print("fail", lang, theme, type(e).__name__, str(e)[:80])
            OUT.write_text(json.dumps(bank, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
