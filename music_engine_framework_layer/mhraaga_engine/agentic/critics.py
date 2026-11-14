"""Critic agents: each scores one aspect of a finished score in [0, 1]. Pure functions, stdlib only, deterministic.
They are the automatic feedback signal; real listener feedback can be added as one more critic."""
from __future__ import annotations

import math
import re
from collections import Counter

from . import library

SCRIPT = {"hindi": "ऀ-ॿ", "marathi": "ऀ-ॿ", "sanskrit": "ऀ-ॿ", "telugu": "ఀ-౿", "gujarati": "઀-૿",
          "kannada": "ಀ-೿", "tamil": "஀-௿", "english": "A-Za-z"}


def _notes(score: dict) -> list[tuple[float, int, float, int]]:
    sa = score["sa"]
    return [(t, round(12 * math.log2(hz / sa)), d, o) for t, hz, d, o, *_ in score["lead"]]


def raga_fidelity(score: dict, brief: dict) -> tuple[float, dict]:
    m, nts = score["meta"], _notes(score)
    scale = set(m["scale"])
    inscale = sum(1 for _, n, _, _ in nts if n % 12 in scale) / len(nts)
    dwell = Counter()
    for _, n, d, _ in nts:
        dwell[n % 12] += d
    mean = sum(dwell.values()) / max(1, len(scale))
    vr = dwell[m["vadi"] % 12] / mean if mean else 0
    vadi = 1.0 if 1.3 <= vr <= 3.0 else max(0.0, 1 - abs(vr - 2.0) / 2.0)
    seq = [n % 12 for _, n, _, _ in nts]
    pk = [n % 12 for n in (m.get("aroha") and _pakad(m) or [])]
    hits = sum(1 for i in range(len(seq) - len(pk) + 1) if pk and seq[i:i + len(pk)] == pk)
    pak = min(1.0, hits / 3)
    return 0.5 * inscale + 0.25 * vadi + 0.25 * pak, {"in_scale": round(inscale, 3), "vadi_ratio": round(vr, 2), "pakad_hits": hits}


def _pakad(meta: dict) -> list[int]:
    from ..ragas import get_raga
    try:
        return get_raga(meta.get("gopi") and f"gopi:{meta['gopi']}" or meta["raga"], meta["sa"])["pakad"]
    except Exception:
        return []


def cadence(score: dict, brief: dict) -> tuple[float, dict]:
    last = max(score["lead"], key=lambda e: e[0])
    on_sa = round(12 * math.log2(last[1] / score["sa"])) % 12 == 0
    sams = [e[0] for e in score["tabla"] if e[3] >= 0.99]
    gap = min((abs(last[0] - s) for s in sams), default=9.0)
    tih = [s for s in score["sections"] if s["name"] == "tihai"]
    return (0.4 * on_sa + 0.6 * max(0.0, 1 - gap / 0.25) + 0.0 * bool(tih)), {"ends_on_sa": on_sa, "sam_gap_s": round(gap, 3)}


def phrase_variety(score: dict, brief: dict) -> tuple[float, dict]:
    seq = [n % 12 for _, n, _, _ in _notes(score)]
    g = [tuple(seq[i:i + 4]) for i in range(len(seq) - 3)]
    ratio = len(set(g)) / max(1, len(g))
    s = min(1.0, ratio / 0.35) if ratio <= 0.8 else max(0.0, 1 - (ratio - 0.8) / 0.2)
    run = max((sum(1 for _ in grp) for _, grp in __import__("itertools").groupby(seq)), default=1)
    return s * (1.0 if run <= 3 else 0.8), {"distinct_4gram": round(ratio, 3), "max_repeat": run}


def contour(score: dict, brief: dict) -> tuple[float, dict]:
    nts = _notes(score)
    iv = [abs(b[1] - a[1]) for a, b in zip(nts, nts[1:])]
    step = sum(1 for i in iv if i <= 2) / max(1, len(iv))
    span = max(n for _, n, _, _ in nts) - min(n for _, n, _, _ in nts)
    s_step = 1.0 if 0.55 <= step <= 0.9 else max(0.0, 1 - min(abs(step - 0.55), abs(step - 0.9)) / 0.4)
    s_span = 1.0 if 9 <= span <= 26 else max(0.0, 1 - min(abs(span - 9), abs(span - 26)) / 12)
    orn = sum(1 for e in score["lead"] if e[3]) / len(score["lead"])
    s_orn = 1.0 if 0.05 <= orn <= 0.45 else 0.6
    return 0.4 * s_step + 0.4 * s_span + 0.2 * s_orn, {"stepwise": round(step, 3), "span": span, "ornaments": round(orn, 3)}


def rhythm(score: dict, brief: dict) -> tuple[float, dict]:
    beat = 60.0 / score["meta"]["tempo"]
    on = [e[0] for e in score["lead"] if score["sections"][1]["t0"] <= e[0] < score["sections"][1]["t1"]]
    if not on:
        return 0.0, {}
    ok = sum(1 for t in on if min(t % (beat / 2), (beat / 2) - t % (beat / 2)) < 0.04) / len(on)
    fill = len(score["tabla"]) / max(1.0, (score["duration"] - score["sections"][1]["t0"]) / beat)
    g0, g1 = score["sections"][1]["t0"], score["sections"][1]["t1"]
    dens = len(on) / max(1.0, (g1 - g0) / beat)  # notes per beat in the gat
    s_dens = 1.0 if 1.1 <= dens <= 2.2 else max(0.0, 1 - min(abs(dens - 1.1), abs(dens - 2.2)) / 1.0)
    lo, hi = (68, 112) if score["meta"]["tala"] in ("keherwa", "dadra", "rupak", "adi") else (54, 92)
    tp = score["meta"]["tempo"]
    s_tempo = 1.0 if lo <= tp <= hi else max(0.0, 1 - min(abs(tp - lo), abs(tp - hi)) / 30)
    return 0.3 * ok + 0.2 * min(1.0, fill) + 0.3 * s_dens + 0.2 * s_tempo, {"on_grid": round(ok, 3), "notes_per_beat": round(dens, 2), "tempo_fit": round(s_tempo, 2)}


def lyrics_fit(score: dict, brief: dict) -> tuple[float, dict]:
    lang = brief.get("language", "")
    lines = [l for l in score["lyrics"] if not l["tag"]]
    if not lines:
        return (1.0, {"instrumental": True}) if not brief.get("lyrics") else (0.0, {"empty": True})
    rng = SCRIPT.get(lang, "A-Za-z")
    text = "".join(l["text"] for l in lines)
    letters = re.findall(r"[^\W\d_]", text)
    right = sum(1 for c in letters if re.match(f"[{rng}]", c)) / max(1, len(letters))
    per = sum(l["dur"] for l in lines) / len(lines)
    pace = 1.0 if 4 <= per <= 16 else max(0.0, 1 - min(abs(per - 4), abs(per - 16)) / 8)
    cps = sum(len(l["text"].replace(" ", "")) for l in lines) / max(1.0, sum(l["dur"] for l in lines))  # sung letters per second
    sing = 1.0 if 2.0 <= cps <= 4.5 else max(0.0, 1 - min(abs(cps - 2.0), abs(cps - 4.5)) / 3.0)
    return 0.45 * right + 0.2 * pace + 0.35 * sing, {"script_match": round(right, 3), "sec_per_line": round(per, 1), "letters_per_s": round(cps, 2)}


def _profile(score: dict) -> list[float]:
    h = [0.0] * 12
    for _, n, d, _ in _notes(score):
        h[n % 12] += d
    z = sum(h) or 1.0
    return [v / z for v in h]


def _cos(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def library_affinity(score: dict, brief: dict) -> tuple[float, dict]:
    refs = [p for p in library.cached() if p["raga_like"]]
    if not refs:
        return 0.5, {"library": "none"}
    mine = _profile(score)
    best = max(refs, key=lambda p: _cos(mine, p["rel_pitch"]))
    c = _cos(mine, best["rel_pitch"])
    t = best["tempo"]
    while t and t > 110:
        t /= 2
    while t and t < 50:
        t *= 2
    close = 1.0 if not t else max(0.0, 1 - abs(score["meta"]["tempo"] - t) / 60)
    return 0.85 * max(0.0, min(1.0, (c - 0.35) / 0.5)) + 0.15 * close, {"nearest": best["file"][:40], "cosine": round(c, 3)}


def poem_form(score: dict, brief: dict) -> tuple[float, dict]:
    """Does it read and pace like the reference poem videos: 10-24 short rhymed lines, 2-4 minutes, soft music without tabla, ends on Sa."""
    lines = [l["text"] for l in score["lyrics"] if not l["tag"]]
    if not lines:
        return 0.0, {"lines": 0}
    words = [len(l.split()) for l in lines]
    avg = sum(words) / len(words)
    n_ok = 1.0 if 10 <= len(lines) <= 24 else max(0.0, 1 - min(abs(len(lines) - 10), abs(len(lines) - 24)) / 10)
    w_ok = 1.0 if 3 <= avg <= 9 else max(0.0, 1 - min(abs(avg - 3), abs(avg - 9)) / 5)
    end = lambda t: re.sub(r"[^\w]", "", t)[-2:]
    pairs = [(lines[i], lines[i + 1]) for i in range(0, len(lines) - 1, 2)]
    rhyme = sum(1 for a, b in pairs if end(a) and end(a) == end(b)) / max(1, len(pairs))
    dur = score["duration"]
    d_ok = 1.0 if 120 <= dur <= 240 else max(0.0, 1 - min(abs(dur - 120), abs(dur - 240)) / 90)
    first, last = score["lyrics"][0]["t"], max(l["t"] for l in score["lyrics"])
    pace = 1.0 if first >= 3 and last <= dur - 8 and not score["tabla"] else 0.4
    sa_end = round(12 * math.log2(max(score["lead"], key=lambda e: e[0])[1] / score["sa"])) % 12 == 0
    return 0.35 * rhyme + 0.15 * n_ok + 0.15 * w_ok + 0.15 * d_ok + 0.15 * pace + 0.05 * sa_end, {"rhyme": round(rhyme, 2), "lines": len(lines), "avg_words": round(avg, 1), "seconds": dur, "no_tabla": not score["tabla"]}


CRITICS = {"raga_fidelity": raga_fidelity, "cadence": cadence, "phrase_variety": phrase_variety, "contour": contour,
           "rhythm": rhythm, "lyrics_fit": lyrics_fit, "library_affinity": library_affinity, "poem_form": poem_form}
WEIGHT = {"raga_fidelity": 0.28, "cadence": 0.05, "phrase_variety": 0.14, "contour": 0.14, "rhythm": 0.12, "lyrics_fit": 0.12, "library_affinity": 0.15, "poem_form": 0.0}


def review(score: dict, brief: dict) -> dict:
    res = {k: f(score, brief) for k, f in CRITICS.items()}
    scores = {k: round(v[0], 4) for k, v in res.items()}
    w = dict(WEIGHT)
    if brief.get("poem"):  # a poem is judged on its form instead of tabla rhythm
        w["rhythm"], w["poem_form"], w["phrase_variety"] = 0.0, 0.2, 0.06
    total = sum(w[k] * scores[k] for k in scores)
    return {"scores": scores, "detail": {k: v[1] for k, v in res.items()}, "reward": round(total, 4)}
