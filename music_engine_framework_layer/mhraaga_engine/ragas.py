"""Raga knowledge. Notes are semitones above Sa (0-11); 12 is the upper Sa, negatives are the lower octave.

Sources (see the Samaveda book): just-intonation ratios (App. S1), the 72 melakartas generated from the
Ri/Ga x Dha/Ni x Ma rule (S4), the 63-raga atlas (App. S2) and the Gopi model of S34 (72 ascent x 72 descent x 3 tonics = 15,552
scale-tonic pairs; ids 1..16000 cover Krishna's traditional 16,000, the last 448 revisit the first ones with a new janya cut).
"""
from __future__ import annotations

import random

RATIO = [1, 16 / 15, 9 / 8, 6 / 5, 5 / 4, 4 / 3, 45 / 32, 3 / 2, 8 / 5, 5 / 3, 9 / 5, 15 / 8]
SVARA = ["Sa", "Re♭", "Re", "Ga♭", "Ga", "Ma", "Ma♯", "Pa", "Dha♭", "Dha", "Ni♭", "Ni"]
TONICS = (183.0, 233.0, 234.0)  # 732, 932, 936 Hz folded down two octaves (book App. S1)
N_GOPI = 16000
_BASE = 72 * 72 * 3

# Ri/Ga pairs per cakra and Dha/Ni pairs, in semitones (Ri1 Ga1 .. Ri3 Ga3)
_RG = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]
_DN = [(8, 9), (8, 10), (8, 11), (9, 10), (9, 11), (10, 11)]
_NAMES = (
    "Kanakangi Ratnangi Ganamurti Vanaspati Manavati Tanarupi Senavati Hanumatodi Dhenuka Natakapriya Kokilapriya Rupavati "
    "Gayakapriya Vakulabharanam Mayamalavagaula Chakravakam Suryakantam Hatakambari Jhankaradhvani Natabhairavi Kiravani "
    "Kharaharapriya Gaurimanohari Varunapriya Mararanjani Charukesi Sarasangi Harikambhoji Dheerasankarabharanam Naganandini "
    "Yagapriya Ragavardhini Gangeyabhushani Vagadheeshwari Shulini Chalanata Salagam Jalarnavam Jhalavarali Navaneetam Pavani "
    "Raghupriya Gavambodhi Bhavapriya Shubhapantuvarali Shadvidhamargini Suvarnangi Divyamani Dhavalambari Namanarayani "
    "Kamavardhini Ramapriya Gamanashrama Vishwambari Shamalangi Shanmukhapriya Simhendramadhyamam Hemavati Dharmavati "
    "Neetimati Kantamani Rishabhapriya Latangi Vachaspati Mechakalyani Chitrambari Sucharitra Jyotiswarupini Dhatuvardhini "
    "Nasikabhushani Kosalam Rasikapriya"
).split()


def melakarta(n: int) -> dict:
    """Melakarta number 1..72 -> its seven notes (semitones)."""
    if not 1 <= n <= 72:
        raise ValueError("melakarta is 1..72")
    m = n - 1
    ma, rest = divmod(m, 36)
    rg, dn = divmod(rest, 6)
    notes = [0, *_RG[rg], 5 + ma, 7, *_DN[dn]]
    return {"number": n, "name": _NAMES[n - 1], "notes": notes}


def _mood_time(notes: set[int]) -> tuple[str, str]:
    """Book heuristics (S11/S27): flat Re+Dha at dawn, sharp Ma at dusk/evening, flat Ga at night."""
    r1, d1, m2, g2, n2 = 1 in notes, 8 in notes, 6 in notes, 3 in notes, 10 in notes
    if r1 and d1 and not m2:
        return "dawn", "devotional, austere"
    if m2 and r1:
        return "dusk", "solemn, longing"
    if m2:
        return "evening", "peaceful, romantic"
    if g2 and n2:
        return "late night", "pathos, deep"
    if g2:
        return "midnight", "serene, majestic"
    return "morning", "joyful, bright"


def _lead(notes: list[int]) -> list[int]:
    return sorted(set(notes))


def _pakad(scale: list[int], vadi: int) -> list[int]:
    s = sorted(set(scale))
    i = min(range(len(s)), key=lambda k: abs(s[k] - vadi))
    lo = s[max(0, i - 2)]
    walk = [lo, s[max(0, i - 1)], s[i], s[min(len(s) - 1, i + 1)], s[i], s[max(0, i - 1)], 0]
    out = [walk[0]]
    for n in walk[1:]:
        if n != out[-1]:
            out.append(n)
    return out


def _pick_samvadi(scale: set[int], vadi: int) -> int:
    for iv in (7, 5):  # vadi/samvadi sit a fifth or fourth apart (book S26)
        if (vadi + iv) % 12 in scale:
            return (vadi + iv) % 12
    return 0


def _build(name: str, aroha: list[int], avaroha: list[int], vadi: int, samvadi: int | None, time: str, mood: str,
           tala: str, pakad: list[int] | None = None, **extra) -> dict:
    scale = set(n % 12 for n in aroha + avaroha)
    samvadi = _pick_samvadi(scale, vadi) if samvadi is None else samvadi
    asc = [n for n in sorted(set(aroha))]
    if asc[-1] != 12 and 0 in asc:
        asc.append(12)
    desc = sorted(set(avaroha), reverse=True)
    if desc[0] != 12 and 0 in desc:
        desc.insert(0, 12)
    return {"name": name, "aroha": asc, "avaroha": desc, "vadi": vadi, "samvadi": samvadi,
            "pakad": pakad or _pakad(asc, vadi), "time": time, "mood": mood, "tala": tala, **extra}


# (name, aroha, avaroha-or-None, vadi, samvadi, time, mood, tala, pakad)
_CLASSICAL = [
    ("Yaman", [-1, 2, 4, 6, 7, 9, 11, 12], None, 4, 11, "evening", "serene, devotional", "teental", [-1, 2, 4, 2, 0]),
    ("Bhoopali", [0, 2, 4, 7, 9, 12], None, 4, 9, "evening", "peaceful", "teental", [4, 2, 0, -3, 0]),
    ("Bhairav", [0, 1, 4, 5, 7, 8, 11, 12], None, 8, 1, "dawn", "serene, austere", "teental", [0, 4, 5, 4, 1, 0]),
    ("Ahir Bhairav", [0, 1, 4, 5, 7, 9, 10, 12], None, 5, 0, "dawn", "serene, bright", "teental", None),
    ("Todi", [0, 1, 3, 6, 7, 8, 11, 12], None, 8, 3, "late morning", "pathos, devotion", "teental", [0, 1, 3, 1, 0]),
    ("Bhairavi", [0, 1, 3, 5, 7, 8, 10, 12], None, 5, 0, "morning", "devotional, pathos", "dadra", None),
    ("Malkauns", [0, 3, 5, 8, 10, 12], None, 5, 0, "midnight", "serene, majestic", "teental", [3, 5, 8, 5, 3, 0]),
    ("Darbari Kanada", [0, 2, 3, 5, 7, 8, 10, 12], None, 2, 7, "midnight", "majestic, deep", "teental", [3, 2, 0, -2, 0]),
    ("Bhimpalasi", [-2, 0, 3, 5, 7, 10, 12], [12, 10, 9, 7, 5, 3, 2, 0], 5, 0, "afternoon", "devotion, pathos", "dadra", None),
    ("Kafi", [0, 2, 3, 5, 7, 9, 10, 12], None, 7, 0, "midnight", "romantic, spring", "dadra", None),
    ("Asavari", [0, 2, 5, 7, 8, 12], [12, 10, 8, 7, 5, 3, 2, 0], 8, 3, "late morning", "pathos, steady", "teental", None),
    ("Khamaj", [0, 2, 4, 5, 7, 9, 11, 12], [12, 10, 9, 7, 5, 4, 2, 0], 4, 11, "night", "romantic, playful", "dadra", None),
    ("Des", [0, 2, 5, 7, 11, 12], [12, 10, 9, 7, 5, 4, 2, 0], 2, 7, "night", "devotional, monsoon longing", "keherwa", None),
    ("Bageshree", [-2, 0, 3, 5, 9, 10, 12], [12, 10, 9, 5, 3, 2, 0], 5, 0, "midnight", "longing, tender", "teental", None),
    ("Durga", [0, 2, 5, 7, 9, 12], None, 5, 0, "night", "calm, heroic grace", "teental", None),
    ("Hamsadhwani", [0, 2, 4, 7, 11, 12], None, 0, 7, "evening", "joyful, auspicious", "teental", None),
    ("Bihag", [-1, 0, 4, 5, 6, 7, 11, 12], [12, 11, 9, 7, 6, 7, 5, 4, 2, 0], 4, 11, "night", "romantic, tender", "teental", None),
    ("Kedar", [0, 5, 7, 9, 11, 12], [12, 11, 9, 7, 6, 5, 2, 0], 5, 0, "night", "devotional, tender", "teental", None),
    ("Marwa", [-1, 1, 4, 6, 9, 11, 12], None, 1, 9, "sunset", "restless, solemn", "rupak", None),
    ("Purvi", [0, 1, 4, 6, 7, 8, 11, 12], None, 4, 11, "sunset", "solemn, grave", "rupak", None),
    ("Puriya Dhanashree", [-1, 1, 4, 6, 7, 8, 11, 12], None, 7, 1, "sunset", "devotional", "rupak", None),
    ("Shree", [0, 1, 6, 7, 11, 12], [12, 11, 8, 7, 6, 4, 1, 0], 1, 7, "sunset", "majestic, serious", "rupak", None),
    ("Jaunpuri", [0, 2, 5, 7, 8, 10, 12], [12, 10, 8, 7, 5, 3, 2, 0], 8, 3, "morning", "grave, tender", "teental", None),
    ("Brindavani Sarang", [0, 2, 5, 7, 11, 12], [12, 10, 7, 5, 2, 0], 2, 7, "midday", "bright, pastoral", "teental", None),
    ("Bilawal", [0, 2, 4, 5, 7, 9, 11, 12], None, 9, 4, "morning", "cheerful, clear", "teental", None),
    ("Miyan Malhar", [0, 2, 5, 7, 9, 10, 11, 12], [12, 10, 9, 7, 5, 3, 2, 0], 5, 0, "rainy season", "rain, grandeur", "jhaptal", None),
    ("Chandrakauns", [0, 3, 5, 8, 11, 12], None, 5, 0, "midnight", "intense, lucid", "teental", None),
    ("Hindol", [0, 4, 6, 9, 11, 12], None, 9, 4, "morning", "joyful, bright", "teental", None),
    ("Basant", [0, 1, 4, 6, 7, 8, 11, 12], None, 0, 7, "spring dawn", "joyful, festive", "teental", None),
    ("Lalit", [0, 1, 4, 5, 6, 8, 11, 12], None, 5, 0, "dawn", "longing, tender", "teental", None),
]


def _classical() -> dict[str, dict]:
    out = {}
    for name, aroha, avaroha, v, s, t, m, tala, pak in _CLASSICAL:
        out[name.lower()] = _build(name, aroha, avaroha or list(aroha), v, s, t, m, tala, pak, kind="classical")
    return out


_CLASS = _classical()


def gopi(n: int, tonic: float | None = None) -> dict:
    """Krishna's 16,000: gopi number 1..16000 -> a deterministic raga (ascent from one melakarta, descent from another, one of
    three tonics, a janya cut that drops up to two notes, vadi/samvadi by the fourth/fifth rule)."""
    if not 1 <= n <= N_GOPI:
        raise ValueError("gopi is 1..16000")
    b = (n - 1) % _BASE
    rest, ti = divmod(b, 3)
    a, d = rest % 72 + 1, rest // 72 + 1
    rng = random.Random(f"gopi-{n}")
    base_a, base_d = melakarta(a)["notes"], melakarta(d)["notes"]
    # janya cut: drop up to two of the non-Sa/Pa degrees (Re, Ga, Ma, Dha, Ni) in each direction
    def cut(seq: list[int]) -> list[int]:
        drop = rng.sample([1, 2, 3, 5, 6], rng.choice([0, 0, 1, 2]))
        return [x for i, x in enumerate(seq) if i not in drop]
    asc_n, desc_n = cut(base_a), cut(base_d)
    notes = set(asc_n) | set(desc_n)
    candidates = [x for x in sorted(notes) if x and ((x + 7) % 12 in notes or (x + 5) % 12 in notes)] or [7]
    vadi = rng.choice(candidates)
    time, mood = _mood_time(notes)
    r = _build(f"Gopī {n:05d}", asc_n + [12], [12] + sorted(desc_n, reverse=True), vadi, None, time, mood,
               rng.choice(["teental", "keherwa", "dadra", "rupak", "jhaptal"]), kind="gopi",
               melakarta_asc=a, melakarta_desc=d, tonic=tonic or TONICS[ti], gopi=n,
               melakarta_names=[melakarta(a)["name"], melakarta(d)["name"]])
    return r


def get_raga(spec: str | int, tonic: float | None = None) -> dict:
    """spec: classical name ('yaman'), 'gopi:1234' / int gopi number, or 'mela:29'."""
    if isinstance(spec, int):
        return gopi(spec, tonic)
    s = str(spec).strip().lower()
    if s.startswith("gopi"):
        digits = "".join(c for c in s if c.isdigit())
        return gopi(int(digits) if digits else 1, tonic)
    if s.startswith("mela"):
        m = melakarta(int("".join(c for c in s if c.isdigit()) or 29))
        return _build(m["name"], m["notes"] + [12], [12] + sorted(m["notes"], reverse=True), 4 if 4 in m["notes"] else 3, None,
                      *_mood_time(set(m["notes"])), "teental", kind="melakarta", melakarta=m["number"])
    if s in _CLASS:
        return dict(_CLASS[s], tonic=tonic) if tonic else dict(_CLASS[s])
    for k, v in _CLASS.items():
        if k.startswith(s) or s in k:
            return dict(v, tonic=tonic) if tonic else dict(v)
    raise KeyError(spec)


def catalog() -> dict:
    return {"classical": [{"name": v["name"], "time": v["time"], "mood": v["mood"], "tala": v["tala"]} for v in _CLASS.values()],
            "melakartas": [{"number": i, "name": melakarta(i)["name"]} for i in range(1, 73)],
            "gopi_count": N_GOPI, "tonics": list(TONICS)}


def hz(sa: float, semitone: int) -> float:
    return sa * RATIO[semitone % 12] * 2 ** (semitone // 12)
