"""Prompt -> music brief, via the Kalkee music agent on the Kalkee AI platform.

Kalkee routes the request to OpenRouter or its SLM tier. If it is unreachable
(or no token is configured) a small keyword fallback keeps generation working
offline; the brief's "source" field records which path produced it.
"""
from __future__ import annotations

import json
import re

import httpx

from . import config

RAGAS = ("yaman", "bhairav", "bhimpalasi", "darbari", "malkauns", "bhupali", "todi", "kafi", "desh", "bageshree")
TAAL_FOR = {"yaman": "teental", "bhairav": "keherwa", "bhimpalasi": "dadra", "darbari": "teental"}


DEITY_DEV = {"krishna": "कृष्ण", "ram": "राम", "shiv": "शिव", "ganesh": "गणेश", "hanuman": "हनुमान", "durga": "दुर्गा"}
LANG_WORDS = {"marathi": ("marathi", "मराठी"), "sanskrit": ("sanskrit", "sloka", "shloka", "mantra", "संस्कृत"),
              "hindi": ("hindi", "हिन्दी", "हिंदी"), "english": ("english",)}


def detect_language(prompt: str, lyrics: str, devotional: bool) -> str:
    """Language the vocals should be in: explicit word in the prompt wins, then the lyrics' script, then the genre."""
    low = prompt.lower()
    for lang, words in LANG_WORDS.items():
        if any(w in low for w in words):
            return lang
    if re.search(r"[\u0900-\u097F]", lyrics or ""):
        return "hindi"
    return "hindi" if devotional else "english"


templates_langs = ("english", "hindi", "marathi", "sanskrit")


def fallback_brief(prompt: str, lyrics: str = "", duration: int = 60, instrumental: bool = False, language: str = "") -> dict:
    low = prompt.lower()
    raga = next((r for r in RAGAS if r in low), "")
    devotional = bool(re.search(r"bhajan|aarti|krishna|ram|shiv|ganesh|hanuman|devi|devotional", low))
    if devotional and not raga:
        raga = "yaman"
    genre = "bhajan" if devotional else "raga" if raga else next(
        (g for g in ("lofi", "pop", "ambient", "cinematic", "folk", "ghazal") if g in low), "ambient")
    mood = next((m for m in ("calm", "joyful", "sad", "energetic", "peaceful", "romantic", "meditative") if m in low),
                "peaceful" if raga else "uplifting")
    language = language if language in templates_langs else detect_language(prompt, lyrics, devotional)
    templates = {  # deity-free: the music, the raga and the hour are the subject
        "hindi": "[Mukhda]\nसुर की नदी बहती जाए\nमन के भीतर शांति लाए\n[Antara]\nसुबह की किरण, शाम की रागिनी\nधुन में खोई हर कहानी",
        "marathi": "[Mukhda]\nसुरांची नदी वाहत जाई\nमनात शांती भरून येई\n[Antara]\nसकाळची किरणे, संध्येची रागिणी\nधुनीत हरवली प्रत्येक कहाणी",
        "sanskrit": "[Mukhda]\nस्वरः प्रवहति शान्तिं ददाति\nमनः प्रसीदति रागेण नित्यम्\n[Antara]\nप्रभाते सन्ध्यायां च गीतम्\nसङ्गीतमेव जीवनस्य साक्षी",
        "english": "[Chorus]\nLet the music carry me softly through the night\n[Verse]\nEvery note a river, every beat a light\nMorning into evening, the raga sings along",
    }
    devotional_lyrics = templates[language]
    return {
        "title": prompt.strip()[:40].title() or "Untitled", "language": language,
        "genre": genre, "raga": raga, "taal": TAAL_FOR.get(raga, "keherwa"),
        "tempo_bpm": {"energetic": 120, "joyful": 108, "calm": 66, "peaceful": 66, "meditative": 54}.get(mood, 84),
        "mood": mood, "instruments": ["tanpura", "tabla", "harmonium", "flute"] if raga else ["pad", "piano"],
        "duration_seconds": duration,
        "lyrics": "" if instrumental else lyrics or (devotional_lyrics if devotional else ""),
    }


def compose(prompt: str, lyrics: str = "", duration: int = 60, instrumental: bool = False, token: str = "", language: str = "") -> dict:
    """Ask Kalkee's orchestrator (which routes to the registered pecova-music-agent) using the caller's Kalkee token."""
    brief, source = None, "fallback"
    token = token or config.AKANADE_TOKEN
    if token:
        try:
            task = prompt + ("\n(instrumental, no lyrics)" if instrumental else "") \
                + (f"\n(write and sing in {language})" if language else "")
            r = httpx.post(f"{config.AKANADE_URL}/api/v1/orchestration/execute", timeout=config.AKANADE_TIMEOUT,
                           headers={"Authorization": f"Bearer {token}"},
                           json={"task": task, "session_id": "music",
                                 "context": {"required_capabilities": ["music_generation"]}})
            r.raise_for_status()
            body = r.json()
            if "pecova-music-agent" in (body.get("selected_agents") or []):
                brief = json.loads(body["result"]["text"])
                source = "akanade"
                from .main import store  # real usage/cost recorded by our agent webhook, keyed by Kalkee's task id
                u = store.get("usage", str(body.get("task_id"))) or {}
                brief["_usage"] = {"in": int(u.get("in", 0)), "out": int(u.get("out", 0)), "estimated": False,
                                   "cost": u.get("cost"), "model": u.get("model", "")}
            else:
                print(f"[brain] Kalkee picked {body.get('selected_agents')}, not the music agent; using fallback")
        except Exception as e:
            print(f"[brain] Kalkee unavailable ({e}); using fallback brief")
    if brief is None:
        brief = fallback_brief(prompt, lyrics, duration, instrumental, language)
    if language in templates_langs:
        brief["language"] = language
    if lyrics:
        brief["lyrics"] = lyrics
    if instrumental:
        brief["lyrics"] = ""
    brief["duration_seconds"] = duration or brief.get("duration_seconds", 60)
    brief["source"] = source
    return brief
