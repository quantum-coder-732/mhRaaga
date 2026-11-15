"""Score composer. A raga is a grammar, so the song follows the classical form:

  alap  - slow, free, drone only; the raga unfolds from Sa upward, resting on vadi/samvadi, with meend (slides)
  gat   - tabla enters; every avartan (tala cycle) opens with the pakad on sam, then rise/fall phrases; vadi and
          samvadi are held twice as long; later avartans move faster
  tihai - the closing phrase played three times so the last note lands exactly on sam

Output is a plain-JSON score the browser renders with Web Audio (tanpura, bansuri/harmonium/veena, tabla).
"""
from __future__ import annotations

import math
import random

from . import autotune, gan, physics
from .ragas import hz
from .tala import TALAS, bol_class


def _walk(path: list[int], a: int, b: int) -> list[int]:
    near = lambda t: min(range(len(path)), key=lambda i: abs(path[i] - t))
    i, j = near(a), near(b)
    return path[i:j + 1] if i <= j else path[j:i + 1][::-1]


class _Phrases:
    def __init__(self, r: dict, rng: random.Random):
        self.r, self.rng = r, rng
        self.asc = sorted(set(r["aroha"]))
        self.desc = sorted(set(r["avaroha"]), reverse=True)
        self.stress = {r["vadi"] % 12, r["samvadi"] % 12}
        self.gan_used, self.gan_score = 0, 0.0

    def _stress(self, seq: list[tuple[int, float]]) -> list[tuple[int, float]]:
        return [(n, b * 2 if n % 12 in self.stress and b <= 1 else b) for n, b in seq]

    def pakad(self) -> list[tuple[int, float]]:
        p = self.r["pakad"]
        return self._stress([(n, 1.0) for n in p[:-1]] + [(p[-1], 2.0)])

    def pakad_head(self, max_beats: float) -> list[tuple[int, float]]:
        """The opening of the pakad, cut so it never fills the whole cycle. In a short tala (keherwa, dadra, adi, rupak) the full pakad used to
        take every beat, so each avartan repeated the same motif and no rise, fall or GAN phrase was ever reached."""
        out, tot = [], 0.0
        for n, b in self.pakad():
            if out and tot + b > max_beats:
                break
            out.append((n, b))
            tot += b
        return out

    def rise(self, fast: bool) -> list[tuple[int, float]]:
        lo = self.asc[: max(2, len(self.asc) // 2)]
        top = self.rng.choice([self.r["vadi"], self.r["samvadi"], self.r["vadi"]])
        w = _walk(self.asc, self.rng.choice(lo), top)
        opts = [0.5, 0.5, 1.0] if fast else [0.5, 1.0, 1.0]
        return self._stress([(n, self.rng.choice(opts)) for n in w])

    def gan_phrase(self, fast: bool):
        g = gan.generate(self.rng, sorted({n % 12 for n in self.r["aroha"] + self.r["avaroha"]}))
        if not g:
            return None
        self.gan_used += 1
        self.gan_score += g[1]
        opts = [0.5, 0.5, 1.0] if fast else [0.5, 1.0, 1.0]
        seq = self._stress([(n, self.rng.choice(opts)) for n in g[0]])
        return seq

    def fall(self, fast: bool) -> list[tuple[int, float]]:
        top = self.rng.choice([self.r["vadi"], self.r["samvadi"], 12 if 12 in self.desc else self.r["vadi"]])
        w = _walk(self.desc, top, 0)
        opts = [0.5, 0.5, 1.0] if fast else [0.5, 1.0, 1.0]
        seq = self._stress([(n, self.rng.choice(opts)) for n in w])
        seq[-1] = (0, 2.0)
        return seq


def _orn(prev: int | None, n: int, rng: random.Random, stress: set[int]) -> int:
    """0 plain, 1 meend (slide from the previous note), 2 kan (grace note touching the note above first)."""
    if prev is not None and abs(n - prev) >= 2 and rng.random() < 0.55:
        return 1
    if n % 12 in stress and rng.random() < 0.4:
        return 2
    return 0


def compose(raga: dict, tala: str = "", tempo: int = 72, duration: int = 90, lyrics: str = "", seed: int | None = None,
            sa: float | None = None, lead: str = "bansuri", instrumental: bool = False, poem: bool = False, human: bool = True,
            style: str = "", ensemble: list | None = None) -> dict:
    tala = tala if tala in TALAS else raga.get("tala", "teental")
    T = TALAS[tala]
    sa = float(sa or raga.get("tonic") or 233.0)
    seed = seed if seed is not None else random.randrange(1 << 30)
    rng = random.Random(seed)
    tempo = max(40, min(180, int(tempo)))
    beat = 60.0 / tempo
    cb = T["beats"]
    cyc = cb * beat
    duration = max(30, min(240, int(duration)))
    P = _Phrases(raga, rng)

    alap_end = duration - 6 * cyc if poem else min(duration * 0.2, 36.0)
    alap_end = max(alap_end, duration * 0.2) if poem else alap_end
    gat_start = max(cyc, math.ceil(alap_end / cyc) * cyc)
    n_av = max(2, int((duration - gat_start - 5 * beat) // cyc))
    end_gat = gat_start + n_av * cyc
    total = end_gat + 6 * beat

    lead_ev: list[list] = []
    prev: list[int | None] = [None]

    def add(t: float, n: int, d: float, force_orn: int | None = None) -> None:
        o = _orn(prev[0], n, rng, P.stress) if force_orn is None else force_orn
        lead_ev.append([round(t, 3), round(hz(sa, n), 2), round(d, 3), o])
        prev[0] = n

    # ---- alap
    asc = P.asc
    pos, reach, k = 0.6, 2, 0
    while pos < gat_start - beat:
        stage = asc[max(0, reach - 3): reach]
        for n in stage + [raga["vadi"] if k % 3 == 2 else stage[-1]]:
            d = beat * rng.choice([1.8, 2.4, 3.0])
            add(pos, n, d * 1.15)
            pos += d
            if pos >= gat_start - beat:
                break
        pos += beat * 0.8
        reach = reach + 1 if reach < len(asc) else 2
        k += 1
    sections = [{"name": "alap", "t0": 0.0, "t1": round(gat_start, 3)}]

    # ---- tihai fragment: last notes of the pakad ending on Sa, played three times so the last note lands on sam
    pk = raga["pakad"][-3:] if raga["pakad"][-1] == 0 else raga["pakad"][-2:] + [0]
    frag = [(n, 0.5) for n in pk[:-1]] + [(0, 1.0)]
    f = sum(b for _, b in frag)
    if 3 * f + 2 > cb - 1:
        frag = frag[-2:]
        f = sum(b for _, b in frag)
    g = max(0.5, min(1.5, (cb - 1 - 3 * f) / 2))
    last_b = frag[-1][1]
    tihai_start = end_gat - (3 * f + 2 * g - last_b) * beat

    # ---- gat
    for av in range(n_av):
        t0 = gat_start + av * cyc
        fast = av >= n_av // 2
        limit = tihai_start - beat * 0.25 if av == n_av - 1 else t0 + cyc - beat * 0.5
        seq = P.pakad_head(max(3.0, cb * 0.45)) if av % 3 else P.pakad_head(max(4.0, cb * 0.6))   # every third cycle states more of the motif
        order = [P.rise, P.fall] if av % 2 == 0 else [P.fall, P.rise]
        t = t0
        gen = 0
        done = False
        while not done:
            for n, b in seq:
                if t + b * beat > limit:
                    done = True
                    break
                add(t, n, b * beat * 0.98)
                t += b * beat
            else:
                gen += 1
                seq = (P.gan_phrase(fast) if rng.random() < 0.3 else None) or order[gen % 2](fast)
                t += beat * (0.5 if gen % 3 == 0 else 0)
    sections.append({"name": "gat", "t0": round(gat_start, 3), "t1": round(tihai_start, 3)})

    t = tihai_start
    for rep in range(3):
        for n, b in frag:
            add(t, n, b * beat * (3.0 if (rep == 2 and n == 0 and b == last_b) else 0.98), 0)
            t += b * beat
        t += g * beat
    sections.append({"name": "tihai", "t0": round(tihai_start, 3), "t1": round(end_gat + 4 * beat, 3)})

    # ---- tabla
    tabla = []
    bols = T["bols"] if not poem else []
    khali = set(T.get("khali", []))
    i = 0
    while not poem and gat_start + i * beat <= end_gat + 1e-6:
        bi = i % cb
        bol = bols[bi]
        tabla.append([round(gat_start + i * beat, 3), bol, bol_class(bol), 1.0 if bi == 0 else 0.7 if bi in khali else 0.82])
        if bi == cb - 1 and (i // cb) % 4 == 3 and gat_start + (i + 1) * beat < end_gat:  # fill: last beat of every 4th avartan
            for j, fb in enumerate(["Dha", "Ge", "Na", "Ti"]):
                tabla.append([round(gat_start + i * beat + j * beat / 4, 3), fb, bol_class(fb), 0.6])
        i += 1

    # ---- lyrics, spread across the gat
    ly = []
    lines = [] if instrumental else [x.strip() for x in lyrics.splitlines() if x.strip()]
    sung = [(x, x[1:-1] if x.startswith("[") and x.endswith("]") else "") for x in lines]
    n_sung = len([s for s in sung if not s[1]])
    if n_sung:
        span = max(cyc, (end_gat - cyc * 0.5) - gat_start) if not poem else max(20.0, total - 14.0)
        step = span / n_sung
        tt = gat_start if not poem else 5.0
        for text, tag in sung:
            if tag:
                ly.append({"t": round(tt, 3), "dur": 0.0, "text": text, "tag": tag})
            else:
                ly.append({"t": round(tt, 3), "dur": round(step * 0.92, 3), "text": text, "tag": ""})
                tt += step

    physics_meta = {"enabled": False}
    if human and lead_ev:                      # physics feel, then auto-tune pulls the drift back to the shruti
        scale = {n % 12 for n in raga["aroha"] + raga["avaroha"]}
        lead_ev = physics.humanise(lead_ev, beat, seed, P.stress, sa, guard_from=tihai_start)
        wander = physics.drift_cents(len(lead_ev), seed)
        body, tail = [], []                     # the tihai keeps exact shruti so the final Sa lands on sam
        for e, c in zip(lead_ev, wander):
            (tail if e[0] >= tihai_start - 1e-6 else body).append([e[0], e[1] * (2.0 ** (c / 1200.0) if e[0] < tihai_start - 1e-6 else 1.0), *e[2:]])
        body, corr = autotune.score(body, sa, scale, 0.75)
        tail, _ = autotune.score(tail, sa, scale, 1.0)
        lead_ev = body + tail
        physics_meta = {"enabled": True, "engine": physics.BACKEND, "rubato_ms": 28, "autotune_cents": round(corr, 2),
                        "gan_phrases": P.gan_used, "gan_score": round(P.gan_score / P.gan_used, 3) if P.gan_used else None}

    second = 7 if any(n % 12 == 7 for n in raga["aroha"]) else 5  # no Pa (Marwa, Puriya): tune the drone to Ma
    return {
        "meta": {"poem": poem, "raga": raga["name"], "tala": tala, "tempo": tempo, "sa": sa, "mood": raga["mood"], "time": raga["time"],
                 "seed": seed, "vadi": raga["vadi"], "samvadi": raga["samvadi"], "kind": raga.get("kind", "classical"),
                 "scale": sorted(set(n % 12 for n in raga["aroha"] + raga["avaroha"])),
                 "physics": physics_meta, "style": style[:200], "ensemble": [e for e in (ensemble or []) if e in ("dholak", "clap", "manjira")], "gopi": raga.get("gopi"), "mela": raga.get("melakarta_names"), "aroha": raga["aroha"], "avaroha": raga["avaroha"]},
        "sa": sa, "lead_voice": lead if lead in ("bansuri", "harmonium", "veena") else "bansuri",
        "drone": {"sa": sa, "second": round(hz(sa, second), 2), "low_sa": round(sa / 2, 2), "pluck": round(beat * 1.9, 3)},
        "lead": lead_ev, "tabla": tabla, "lyrics": ly, "sections": sections, "duration": round(total, 2),
    }
