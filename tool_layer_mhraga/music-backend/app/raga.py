"""Raga grammar for the procedural bed (the 'Suno-like' logic, done the Hindustani way).

A raga is not just a scale: it has an aroha/avaroha (how it climbs and falls), a vadi (king note) and samvadi
(minister) that get the long, stressed notes, a pakad (signature phrase) every avartan returns to, and a
form: alap (slow, free, drone only) -> gat (tabla enters, phrases follow the cycle) -> tihai (a phrase thrice,
landing on sam). Notes are semitones above Sa; 12 is the upper Sa, negatives are the lower octave.
"""
from __future__ import annotations

import random

RAGAS: dict[str, dict] = {
    "yaman": dict(aroha=[-5, -3, -1, 2, 4, 6, 7, 9, 11, 12], avaroha=[12, 11, 9, 7, 6, 4, 2, 0, -1, -3, -5, 0],
                  vadi=4, samvadi=11, pakad=[-1, 2, 4, 6, 4, 2, 0], time="evening"),
    "bhairav": dict(aroha=[0, 1, 4, 5, 7, 8, 11, 12], avaroha=[12, 11, 8, 7, 5, 4, 1, 0],
                    vadi=8, samvadi=1, pakad=[0, 1, 4, 5, 4, 1, 0], time="dawn"),
    "bhimpalasi": dict(aroha=[-2, 0, 3, 5, 7, 10, 12], avaroha=[12, 10, 9, 7, 5, 3, 2, 0],
                       vadi=5, samvadi=0, pakad=[-2, 0, 5, 3, 5, 3, 2, 0], time="afternoon"),
    "darbari": dict(aroha=[0, 2, 3, 5, 7, 8, 10, 12], avaroha=[12, 10, 8, 7, 5, 3, 2, 0],
                    vadi=2, samvadi=7, pakad=[2, 3, 2, 0, 2, 0, -2], time="late night"),
    "malkauns": dict(aroha=[0, 3, 5, 8, 10, 12], avaroha=[12, 10, 8, 5, 3, 0],
                     vadi=5, samvadi=0, pakad=[3, 5, 8, 5, 3, 0], time="midnight"),
    "bhupali": dict(aroha=[0, 2, 4, 7, 9, 12], avaroha=[12, 9, 7, 4, 2, 0],
                    vadi=7, samvadi=0, pakad=[4, 7, 9, 7, 4, 2, 0], time="evening"),
    "todi": dict(aroha=[0, 1, 3, 6, 7, 8, 11, 12], avaroha=[12, 11, 8, 7, 6, 3, 1, 0],
                 vadi=8, samvadi=3, pakad=[0, 1, 3, 1, 0, -1, 0], time="morning"),
    "kafi": dict(aroha=[0, 2, 3, 5, 7, 9, 10, 12], avaroha=[12, 10, 9, 7, 5, 3, 2, 0],
                 vadi=7, samvadi=0, pakad=[0, 2, 3, 5, 7, 5, 3, 2, 0], time="night"),
    "desh": dict(aroha=[0, 2, 5, 7, 11, 12], avaroha=[12, 10, 9, 7, 5, 4, 2, 0],
                 vadi=2, samvadi=7, pakad=[2, 5, 7, 5, 4, 2, 0], time="night"),
    "bageshree": dict(aroha=[-2, 0, 3, 5, 9, 10, 12], avaroha=[12, 10, 9, 7, 5, 3, 2, 0],
                      vadi=5, samvadi=0, pakad=[-2, 0, 3, 5, 3, 2, 0], time="midnight"),
}


def _near(notes: list[int], target: int) -> int:
    return min(range(len(notes)), key=lambda i: abs(notes[i] - target))


def _walk(path: list[int], a: int, b: int) -> list[int]:
    """Notes along `path` (aroha or avaroha order) from the note nearest a to the note nearest b."""
    i, j = _near(path, a), _near(path, b)
    return path[i:j + 1] if i <= j else path[j:i + 1][::-1]


def phrases(raga: str, seed: int) -> dict:
    """Pre-built phrases for the form, as lists of (semitone, beats)."""
    r = RAGAS[raga]
    rng = random.Random(seed)
    sc = sorted(set(r["aroha"]))
    pak = [(n, 1.0) for n in r["pakad"]]
    pak[-1] = (pak[-1][0], 2.0)

    def ornament(seq: list[tuple[int, float]]) -> list[tuple[int, float]]:
        # vadi and samvadi are the stressed notes: held twice as long
        return [(n, b * 2 if n % 12 in (r["vadi"] % 12, r["samvadi"] % 12) else b) for n, b in seq]

    def rise() -> list[tuple[int, float]]:
        start = rng.choice(sc[: len(sc) // 2])
        top = rng.choice([r["vadi"], r["samvadi"], r["vadi"] + 12 if r["vadi"] + 12 <= 14 else r["vadi"]])
        w = _walk(r["aroha"], start, top)
        return ornament([(n, rng.choice([0.5, 1.0, 1.0])) for n in w])

    def fall() -> list[tuple[int, float]]:
        top = rng.choice([r["vadi"], r["samvadi"], 12 if 12 in r["avaroha"] else r["vadi"]])
        w = _walk(r["avaroha"], top, 0)
        seq = ornament([(n, rng.choice([0.5, 1.0, 1.0])) for n in w])
        seq[-1] = (0, 2.0)
        return seq

    return {"pakad": ornament(pak), "rise": rise, "fall": fall, "sa": r["pakad"][0], "tihai": pak[:3]}


def form(total: float, raga: str, seed: int, beat: float, cycle_beats: int) -> list[tuple[float, int, float, str]]:
    """Whole-song melody: [(start_seconds, semitone, seconds, section)] following alap -> gat -> tihai."""
    P = phrases(raga, seed)
    notes: list[tuple[float, int, float, str]] = []
    alap_end = total * 0.18
    gat_end = total - cycle_beats * beat * 1.5
    pos = 1.0
    # alap: slow, breathing, only the pakad's skeleton and the vadi, no pulse
    skel = [n for n, _ in P["pakad"]]
    i = 0
    while pos < alap_end:
        n = skel[i % len(skel)]
        d = beat * 2.5
        notes.append((pos, n, d * 1.2, "alap"))
        pos += d + beat * 0.5
        i += 1
    pos = max(pos, alap_end)
    # gat: snap each phrase to the next beat; pakad opens every avartan, then rise, fall, pakad
    order = ["pakad", "rise", "fall", "pakad", "rise", "fall"]
    k = 0
    while pos < gat_end:
        kind = order[k % len(order)]
        seq = P["pakad"] if kind == "pakad" else P[kind]()
        for n, b in seq:
            d = b * beat
            if pos + d > gat_end:
                break
            notes.append((pos, n, d, "gat"))
            pos += d
        pos += beat * (1 if k % 3 == 2 else 0.5)  # breath after the fall
        pos = round(pos / beat) * beat
        k += 1
    # tihai: signature fragment three times with a gap, last note lands on Sa at sam
    frag = P["tihai"]
    for _ in range(3):
        for n, b in frag:
            notes.append((pos, n, b * beat, "tihai"))
            pos += b * beat
        pos += beat
    notes.append((pos, 0, beat * 4, "tihai"))
    return notes


def sing_notes(raga: str, seed: int, k: int, line_no: int) -> list[int]:
    """k notes for one sung line: opens on the pakad, climbs to the vadi, falls home; the last syllable rests on Sa
    (or the samvadi on every other line, so verses answer each other)."""
    P = phrases(raga, seed)
    seq = [n for n, _ in P["pakad"]]
    seq += [n for n, _ in P["rise"]()]
    seq += [n for n, _ in P["fall"]()]
    out = [seq[i % len(seq)] for i in range(k)]
    out[-1] = 0 if line_no % 2 == 0 else RAGAS[raga]["samvadi"] % 12 if RAGAS[raga]["samvadi"] % 12 < 8 else 0
    return out
