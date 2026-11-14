"""Prompt -> music brief. OpenRouter (GLM flash, DeepSeek flash fallback) plans the song as JSON; if the model is unreachable or
returns junk, keyword rules produce the brief so the app still works offline. `source` records which path ran."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request

from .ragas import _CLASS, N_GOPI, get_raga
from .tala import TALAS

MODELS = ("z-ai/glm-5.3-flash", "deepseek/deepseek-v4-flash")
LANGS = ("hindi", "marathi", "sanskrit", "english", "telugu", "gujarati", "kannada", "tamil")
LEADS = ("bansuri", "harmonium", "veena")
KRISHNA = re.compile(r"krish|kanha|govind|madhav|gopi|gopal|radha|bansuri|flute|vrind|murali|ghanshyam|कृष्ण|कान्हा|गोपी|राधा", re.I)

LYRICS = {
    "hindi": "[Mukhda]\nबंसी की धुन पर नाचे मन मेरा\nकान्हा की मुरली में खोया सवेरा\n[Antara]\nगोपियाँ दौड़ीं यमुना किनारे\nराग हज़ार, एक ही पुकारे",
    "marathi": "[Mukhda]\nबासरीच्या सुरात हरवलं मन\nकान्हाच्या धुनीत रंगलं जीवन\n[Antara]\nगोपी धावल्या यमुनेच्या काठी\nसूर हजार, एकच ओठी",
    "sanskrit": "[Mukhda]\nवंशीरवः कृष्णस्य मनो हरति\nरागसहस्रं हृदि प्रवहति\n[Antara]\nगोपिकाः यमुनातटे नृत्यन्ति\nसर्वे स्वराः एकं कृष्णं स्तुवन्ति",
    "english": "[Chorus]\nThe flute calls and every heart replies\nA thousand ragas under moonlit skies\n[Verse]\nSa to Sa, the river sings along\nOne breath of Krishna turns the night to song",
}
PLAIN = {
    "hindi": "[Mukhda]\nसुर की नदी बहती जाए\nमन के भीतर शांति लाए\n[Antara]\nसुबह की किरण, शाम की रागिनी\nधुन में खोई हर कहानी",
    "marathi": "[Mukhda]\nसुरांची नदी वाहत जाई\nमनात शांती भरून येई\n[Antara]\nसकाळची किरणे, संध्येची रागिणी\nधुनीत हरवली प्रत्येक कहाणी",
    "sanskrit": "[Mukhda]\nस्वरः प्रवहति शान्तिं ददाति\nमनः प्रसीदति रागेण नित्यम्\n[Antara]\nप्रभाते सन्ध्यायां च गीतम्\nसङ्गीतमेव जीवनस्य साक्षी",
    "english": "[Chorus]\nLet the music carry me softly through the night\n[Verse]\nEvery note a river, every beat a light\nMorning into evening, the raga sings along",
}
MOOD_RAGA = {"calm": "Bhoopali", "peaceful": "Yaman", "devotional": "Bhairavi", "sad": "Todi", "romantic": "Bihag", "joyful": "Hindol",
             "energetic": "Khamaj", "meditative": "Malkauns", "morning": "Bhairav", "dawn": "Bhairav", "evening": "Yaman",
             "night": "Darbari Kanada", "rain": "Miyan Malhar", "spring": "Basant"}
MOOD_TEMPO = {"calm": 62, "peaceful": 66, "meditative": 54, "sad": 60, "devotional": 70, "romantic": 78, "joyful": 104, "energetic": 118}


def gopi_for(text: str) -> int:
    return int(hashlib.sha256(text.strip().lower().encode()).hexdigest(), 16) % N_GOPI + 1


from . import poems as _poems
from .lyrics_bank import MOOD_THEME as MOOD_THEME_, make_lyrics as _make_lyrics


def detect_language(prompt: str) -> str:
    low = prompt.lower()
    for lang, words in {"marathi": ("marathi", "मराठी"), "sanskrit": ("sanskrit", "shloka", "mantra", "संस्कृत"),
                        "hindi": ("hindi", "हिन्दी", "हिंदी", "bhajan", "भजन"), "english": ("english",),
                        "telugu": ("telugu", "తెలుగు"), "gujarati": ("gujarati", "ગુજરાતી"), "kannada": ("kannada", "ಕನ್ನಡ"), "tamil": ("tamil", "தமிழ்")}.items():
        if any(w in low for w in words):
            return lang
    for lang, rng in (("telugu", "ఀ-౿"), ("gujarati", "઀-૿"), ("kannada", "ಀ-೿"), ("tamil", "஀-௿")):
        if re.search(f"[{rng}]", prompt):
            return lang
    if re.search(r"[ऀ-ॿ]", prompt):
        return "hindi"
    return "hindi" if KRISHNA.search(low) else "english"


def fallback(prompt: str, opts: dict) -> dict:
    low = prompt.lower()
    krishna = bool(KRISHNA.search(low))
    raga = next((r["name"] for r in _CLASS.values() if r["name"].lower() in low), "")
    mood = next((m for m in MOOD_RAGA if m in low), "devotional" if krishna else "peaceful")
    if not raga:
        raga = f"gopi:{gopi_for(prompt)}" if krishna else MOOD_RAGA[mood]
    lang = opts.get("language") or detect_language(prompt)
    if opts.get("poem"):
        got = _poems.pick(lang, prompt)
        if got:
            return {"title": got[0], "raga": "Yaman" if "krish" not in low else f"gopi:{gopi_for(prompt)}", "tala": "dadra", "tempo_bpm": 58, "mood": "tender", "language": lang,
                    "lead": "bansuri", "lyrics": got[1], "poem": True}
    return {"title": prompt.strip()[:44].title() or "Untitled", "raga": raga, "tala": "", "tempo_bpm": MOOD_TEMPO.get(mood, 72),
            "mood": mood, "language": lang, "lead": "bansuri" if krishna else "harmonium",
            "lyrics": (LYRICS if krishna else PLAIN)[lang] if lang in LYRICS else _make_lyrics(lang, "krishna" if krishna else MOOD_THEME_.get(mood, ""))[0]}


SYSTEM = (
    "You are the music planner of mhRaaga, a Hindustani raga composer. Reply with ONE JSON object only, no prose, with keys: "
    'title (<=40 chars), raga, tala, tempo_bpm (integer 50-140), mood (one word), language (hindi|marathi|sanskrit|english|telugu|gujarati|kannada|tamil), '
    'lead (bansuri|harmonium|veena), lyrics (string). '
    "raga must be exactly one of: {ragas}; or 'gopi:N' with N an integer 1..16000 (Krishna's sixteen thousand ragas: one per gopi, "
    "use it for Krishna/flute/gopi themes or when the user wants a unique raga); or 'mela:N' with N 1..72. "
    "tala must be one of: {talas}. Match the raga to the mood and hour the user asks for. "
    "lyrics: 4-8 short lines in the chosen language (native script: Devanagari for hindi/marathi/sanskrit, Telugu, Gujarati, Kannada or Tamil script), tagged with [Mukhda] and [Antara] "
    "(or [Chorus]/[Verse] for english), singable, no markdown. Empty string if the user wants an instrumental."
)


def _call(model: str, prompt: str, key: str, timeout: float) -> dict:
    body = json.dumps({"model": model, "temperature": 0.8, "max_tokens": 1800, "response_format": {"type": "json_object"},
                       "messages": [{"role": "system", "content": SYSTEM.format(ragas=", ".join(r["name"] for r in _CLASS.values()),
                                                                                  talas=", ".join(TALAS))},
                                    {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "HTTP-Referer": "https://mhraaga.app", "X-Title": "mhRaaga"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    text = data["choices"][0]["message"]["content"]
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    out = json.loads(text[text.index("{"): text.rindex("}") + 1])
    out["_usage"] = data.get("usage", {})
    return out


def _clean(b: dict, prompt: str, opts: dict) -> dict:
    out = fallback(prompt, opts)
    for k in ("title", "mood", "lyrics"):
        if isinstance(b.get(k), str) and (b[k].strip() or k == "lyrics"):
            out[k] = b[k].strip()[: 3000 if k == "lyrics" else 60]
    try:
        get_raga(b.get("raga", ""))
        out["raga"] = b["raga"]
    except Exception:
        pass
    if b.get("tala") in TALAS:
        out["tala"] = b["tala"]
    if isinstance(b.get("tempo_bpm"), (int, float)):
        out["tempo_bpm"] = int(max(50, min(140, b["tempo_bpm"])))
    if b.get("language") in LANGS:
        out["language"] = b["language"]
    if b.get("lead") in LEADS:
        out["lead"] = b["lead"]
    return out


def make_brief(prompt: str, opts: dict | None = None, api_key: str = "", timeout: float = 11.0) -> dict:
    opts = opts or {}
    brief, source, usage = None, "fallback", {}
    if api_key:
        for model in MODELS:
            try:
                raw = _call(model, prompt + (f"\n(language: {opts['language']})" if opts.get("language") else "") +
                            ("\n(spoken poem: write 14-18 short rhymed lines of 4-9 words, plain intimate words, gentle imagery like flute, moon, river, hands; tag [Verse]/[Chorus] every 4 lines)" if opts.get("poem") else "") +
                            ("\n(instrumental: no lyrics)" if opts.get("instrumental") else ""), api_key, timeout)
                brief, source, usage = _clean(raw, prompt, opts), model, {"model": model, **raw.get("_usage", {})}
                break
            except Exception as e:
                print(f"[brief] {model} failed: {type(e).__name__}: {str(e)[:120]}")
    if brief is None:
        brief = fallback(prompt, opts)
    # explicit choices in the UI always win over the model
    if opts.get("raga"):
        brief["raga"] = opts["raga"]
    if opts.get("tala") in TALAS:
        brief["tala"] = opts["tala"]
    if opts.get("tempo"):
        brief["tempo_bpm"] = int(opts["tempo"])
    if opts.get("language") in LANGS:
        brief["language"] = opts["language"]
    if opts.get("lead") in LEADS:
        brief["lead"] = opts["lead"]
    if opts.get("lyrics"):
        brief["lyrics"] = opts["lyrics"]
    if opts.get("instrumental"):
        brief["lyrics"] = ""
    if opts.get("poem"):
        brief["poem"], brief["tempo_bpm"] = True, min(brief.get("tempo_bpm", 58), 66)
        if source == "fallback" and not brief.get("lyrics"):
            got = _poems.pick(brief["language"], prompt)
            brief["lyrics"] = got[1] if got else brief.get("lyrics", "")
    brief["source"], brief["usage"] = source, usage
    return brief


TARGETS = ("hindi", "marathi", "english", "telugu", "gujarati", "kannada", "tamil", "bengali", "punjabi", "urdu", "sanskrit",
           "spanish", "french", "german", "italian", "portuguese", "russian", "japanese", "korean", "chinese", "arabic")


def translate(text: str, to: str, api_key: str, timeout: float = 25.0) -> str:
    """Translate `text` into `to` (one of TARGETS) with the same OpenRouter models. Raises RuntimeError if no model answers."""
    if to not in TARGETS:
        raise ValueError("unsupported language")
    if not api_key:
        raise RuntimeError("Translation needs the language model, which is not configured.")
    msgs = [{"role": "system", "content": f"Translate the user's text into {to}, in its native script. Keep meaning, tone and line breaks. "
                                          "Reply with the translation only, no notes, no quotes."},
            {"role": "user", "content": text}]
    for model in MODELS:
        try:
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", method="POST",
                                         data=json.dumps({"model": model, "temperature": 0.2, "max_tokens": 2500, "messages": msgs}).encode(),
                                         headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                                                  "HTTP-Referer": "https://mhraaga.app", "X-Title": "mhRaaga"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.load(r)["choices"][0]["message"]["content"].strip()
            if out:
                return out
        except Exception as e:
            print(f"[translate] {model} failed: {type(e).__name__}: {str(e)[:100]}")
    raise RuntimeError("Translation is unavailable right now. Try again in a moment.")


def chat(system: str, user: str, api_key: str, max_tokens: int = 1800, as_json: bool = False, timeout: float = 24.0) -> str:
    """One LLM turn through the same OpenRouter models (fallback order). Raises RuntimeError when none answers."""
    if not api_key:
        raise RuntimeError("The language model is not configured.")
    for model in MODELS:
        try:
            body = {"model": model, "temperature": 0.8, "max_tokens": max_tokens, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            if as_json:
                body["response_format"] = {"type": "json_object"}
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(), method="POST",
                                         headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "HTTP-Referer": "https://mhraaga.app", "X-Title": "mhRaaga"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = (json.load(r)["choices"][0]["message"]["content"] or "").strip()
            if out:
                return out
        except Exception as e:
            print(f"[chat] {model} failed: {type(e).__name__}: {str(e)[:100]}")
    raise RuntimeError("The language model did not answer. Try again in a moment.")
