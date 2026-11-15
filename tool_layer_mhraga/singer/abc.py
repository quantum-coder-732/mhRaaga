"""mhRaaga score -> ABC notation for YuE2 (two voices, Vocal and Ins, 4/4, sixteenth-note grid), so the sung melody is the raga's own.

Only the melody is supplied (YuE2's cot="melody" mode); the model arranges the accompaniment. Each lyric line gets `bars_per_line` bars of the
song's gat melody, taken in order, quantised to sixteenth notes at the song's tempo. Pitch: Sa is placed on G3 (a comfortable male range);
komal and tivra svaras become flats and sharps. Honest limit: ABC is equal-tempered, so the just-intonation shruti is rounded to the nearest semitone."""
from __future__ import annotations

SA_MIDI = 55                                   # G3
NAMES = ["C", "_D", "D", "_E", "E", "F", "^F", "G", "_A", "A", "_B", "B"]


def _abc_pitch(midi: int, seen: dict) -> str:
    """One note name with its octave marks and, when the bar needs it, an explicit natural."""
    pc, octv = midi % 12, midi // 12 - 1        # octave 4 = middle C
    name = NAMES[pc]
    acc, letter = (name[0], name[1]) if len(name) == 2 else ("", name)
    if acc:
        seen[letter] = acc
    elif letter in seen:
        acc = "="                                # a sharp or flat earlier in this bar would otherwise carry over
        seen.pop(letter)
    s = acc + letter
    if octv >= 5:
        s = acc + letter.lower() + "'" * (octv - 5)
    else:
        s += "," * (4 - octv)
    return s


def _dur(n: int) -> str:
    return "" if n == 1 else str(n)


def _bars(slots: list, n_bars: int) -> str:
    """slots: per sixteenth, ('start', midi) / ('hold',) / None for rests. Returns bar text with ties across bar lines."""
    out, i = [], 0
    for b in range(n_bars):
        seen, toks, pos = {}, [], b * 16
        while pos < (b + 1) * 16:
            s = slots[pos]
            if s is None:
                n = 1
                while pos + n < (b + 1) * 16 and slots[pos + n] is None:
                    n += 1
                toks.append("z" + _dur(n)); pos += n
            else:
                midi, n = s[1], 1
                while pos + n < (b + 1) * 16 and slots[pos + n] is not None and slots[pos + n][0] == "hold":
                    n += 1
                tie = "-" if pos + n == (b + 1) * 16 and pos + n < len(slots) and slots[pos + n] is not None and slots[pos + n][0] == "hold" else ""
                toks.append(_abc_pitch(midi, seen) + _dur(n) + tie); pos += n
        out.append("".join(toks))
    return out


def score_to_abc(score: dict, n_lines: int, bars_per_line: int = 2, sections: list | None = None, title: str = "") -> str:
    """sections: lyric line counts per section, for example [4, 4, 2, 4]; each becomes one block of the score."""
    tempo = int(score["meta"]["tempo"]); beat = 60.0 / tempo; sixteenth = beat / 4.0
    sa = float(score["sa"]); gat = next((s for s in score.get("sections", []) if s["name"] == "gat"), {"t0": 0.0})
    notes = [n for n in score["lead"] if n[0] >= gat["t0"] - 1e-6]
    import math
    total_bars = n_lines * bars_per_line
    slots: list = [None] * (total_bars * 16)
    t0 = notes[0][0] if notes else 0.0
    last_end = 0
    for t, hz, d, *_ in notes:
        s = int(round((t - t0) / sixteenth))
        if s >= len(slots):
            break
        if s < last_end:                                      # monophonic: a new note cuts the old one
            s = last_end
        e = min(len(slots), max(s + 1, s + int(round(d / sixteenth))))
        midi = SA_MIDI + int(round(12 * math.log2(hz / sa)))
        midi = max(43, min(79, midi))                         # keep it singable: G2 to G5
        slots[s] = ("start", midi)
        for k in range(s + 1, e):
            slots[k] = ("hold", midi)
        last_end = e
    sections = sections or [n_lines]
    head = [f"X:1", "T:", "M:4/4", "L:1/16", f"Q:1/4={tempo}", 'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"', 'V: Ins clef=treble name="Ins Melody" snm="Inst."', "K:C"]
    body, bar = [], 0
    for si, cnt in enumerate(sections):
        nb = cnt * bars_per_line
        bars = _bars(slots[bar * 16:(bar + nb) * 16], nb)
        for g in range(0, nb, 4):                      # YuE2 reads the score in groups of 1 to 4 bars
            grp = bars[g:g + 4]
            body += [f"% {'verse' if si % 2 == 0 else 'chorus'}", "V: Vocal", "|".join(grp) + "|", "V: Ins", f"Z{len(grp)}|"]
        bar += nb
    return "\n".join(head + body) + "\n"
