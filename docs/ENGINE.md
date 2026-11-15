# The music engine, module by module

Package: `music_engine_framework_layer/mhraaga_engine/`. Pure Python, no web code. The Lambda imports it; the song factory and the tests use it directly.
Data flows in this order: **brief** (what to make) -> **ragas** and **tala** (the grammar) -> **compose** (the score) -> **physics**, **gan** and **autotune** (how it feels).

```
 prompt ─► brief.py ─► {raga, tala, tempo, mood, language, lead, lyrics}
                          │
          ragas.py ◄──────┤ get_raga()            tala.py ◄── TALAS
                          ▼
                     compose.py  ── phrases ◄── gan.py (some phrases)
                          │
                          ├─ physics.humanise()  rubato, weight, meend, drift   (physics.py, Box2D)
                          ├─ autotune.score()    pull pitch to the shruti        (autotune.py)
                          ▼
                     score JSON  { sa, drone, lead[], tabla[], lyrics[], sections[], meta }
```

## compose.py — the score composer
`compose(raga, tala="", tempo=72, duration=90, lyrics="", seed=None, sa=None, lead="bansuri", instrumental=False, poem=False, human=True) -> dict`

A raga is treated as a grammar, so the song follows the classical form:

| Section | What happens |
|---|---|
| **alap** | Drone only, free time. The raga unfolds from Sa upward in stages, resting on the vadi every third phrase, with long notes (1.8 to 3 beats) and meend. About 20% of the song, at most 36 s (a poem keeps a longer alap to leave room for the spoken words). |
| **gat** | The tabla enters. Each avartan (tala cycle) opens on sam with the start of the **pakad** (at most 45% of the cycle, and 60% every third cycle, so it is stated but never fills the cycle), then alternates **rise** and **fall** phrases. The vadi and samvadi are held twice as long. The second half of the song moves faster (more half-beat notes). 30% of the time a **GAN phrase** replaces a rise/fall. |
| **tihai** | The closing figure (the end of the pakad, ending on Sa) is played three times with gaps sized so that the last note lands exactly on sam. |

- **Notes** are `[time, hz, duration, ornament]` (then `velocity` and `glide` are added by physics). Ornament: 0 plain, 1 **meend** (slide from the previous note, chosen 55% of the time on leaps of 2 or more semitones), 2 **kan** (a grace note from above, 40% on stressed notes).
- **Tabla** follows the tala's bol per beat (`tala.py`). Beat 1 (sam) is loudest (1.0), the khali beat is softer (0.7), others 0.82. Every fourth avartan ends with a four-stroke fill (Dha Ge Na Ti).
- **Lyrics** are spread over the gat (or over the whole song for a poem), one line per equal slot; `[Mukhda]`-style tags become timed headings with no duration.
- **Tempo** is clamped 40 to 180 bpm, **duration** 30 to 240 s. The same `seed` always gives the same song.
- After composing, if `human=True`, `physics.humanise` and `autotune.score` run (the tihai is exempt so sam stays exact). The result is recorded in `meta.physics` (engine, rubato limit, mean auto-tune correction in cents, GAN phrases used and their mean score).

> **Fixed on 15 Nov 2026.** In short talas (keherwa, dadra, adi, rupak, the bhajan talas) the whole pakad used to fill every cycle, so the gat repeated one motif and the GAN was never reached. For Yaman in keherwa, 4 of 17 cycles were different. Now 17 of 17 are, and the GAN supplies 5 to 11 phrases per song. A regression test (`test_short_talas_do_not_repeat_one_motif`) guards it.

## ragas.py — raga knowledge
Notes are semitones above Sa (0 to 11; 12 is the upper Sa, negatives the lower octave). Pitch uses **just intonation** (`RATIO`: 1, 16/15, 9/8, 6/5, 5/4, 4/3, 45/32, 3/2, 8/5, 5/3, 9/5, 15/8). Three tonics are used: 183, 233 and 234 Hz.

| Source of a raga | How |
|---|---|
| **Classical (30)** | A hand-written table: name, ascent, descent, vadi, samvadi, time of day, mood. Yaman, Bhairavi, Todi, Bhoopali, Kafi, Marwa and others. |
| **Melakarta 1 to 72** | Generated from the rule: Ri/Ga pair (6) x Dha/Ni pair (6) x Ma (2). `get_raga("mela:29")`. |
| **Gopi 1 to 16000** | Ascent from one melakarta, descent from another, one of three tonics (72 x 72 x 3 = 15,552 combinations; the last 448 ids revisit early ones with a new janya cut). The vadi and samvadi are a fourth or fifth apart. Deterministic: the same number always gives the same raga. About 15,947 are distinct. |

Mood and time of day come from book heuristics: flat Re and Dha suggest dawn, a sharp Ma dusk, a flat Ga night. `get_raga(spec)` takes a name, `gopi:1234`, a bare number, or `mela:29`. `catalog()` lists everything for the Ragas page.

## tala.py — rhythm cycles
`TALAS` holds, per tala, the number of beats, the vibhag (sections), the sam, the khali beats and a bol per beat:

| Tala | Beats | Sections | Khali |
|---|---|---|---|
| teental | 16 | 4+4+4+4 | beat 9 |
| keherwa | 8 | 4+4 | beat 5 |
| dadra | 6 | 3+3 | beat 4 |
| rupak | 7 | 3+2+2 | sam |
| jhaptal | 10 | 2+3+2+3 | beat 6 |
| ektal | 12 | 2 x 6 | beats 3 and 7 |
| adi | 8 | 4+2+2 | beat 5 |

`bol_class(bol)` says which drum plays a bol: dha, dhin, dhi use **both**; na, ti, tin, ta, ra, ki, tu the **right** (dayan); ge, ka, kat the **left** (bayan). The synths turn each bol into a stroke (see [SOUND.md](SOUND.md)).

## brief.py — prompt to plan
`make_brief(prompt, opts, api_key, timeout=11)` returns the plan the composer needs: raga, tala, tempo, mood, language, lead instrument, title and lyrics.
1. If a key is set it asks OpenRouter, trying `z-ai/glm-5.3-flash` then `deepseek/deepseek-v4-flash`. The system prompt makes the model reply with one JSON object; `_clean` validates every field (raga must exist, tempo in range, language and lead from the allowed lists).
2. If both models fail or reply with junk, **keyword rules** (`fallback`) pick a raga from the mood (calm to Bhoopali, devotional to Bhairavi, sad to Todi, romantic and so on), a tempo from the mood, a gopi raga when the prompt names Krishna, Radha, flute and similar words, and a bank lyric in the right language. `source` says which path ran (`fallback` or the model name).
3. Choices made in the UI (`raga`, `tala`, `tempo`, `language`, `lead`, your own `lyrics`, `instrumental`, `poem`) always override the model. A poem forces a slow tempo (at most 66 bpm).

Also here: `detect_language(prompt)` (by script), `translate(text, to, key)` (21 target languages) and `chat(system, user, key)` (one model turn, used by the studio). Languages for songs: Hindi, Marathi, Sanskrit, English, Telugu, Gujarati, Kannada, Tamil.

## poems.py and lyrics_bank.py — words without a model
- **`poems_bank.json` and `poems.pick(language, hint)`**: short rhymed spiritual-love poems per language, used when a poem is asked for and the model is not available. `rhyme()` is a cheap rhyme test (do the two lines of a couplet end in the same last two letters); `tag()` adds `[Verse]` and `[Chorus]` tags.
- **`lyrics_bank.make_lyrics(language, theme)`**: couplets in seven languages in native script, grouped by theme (dawn, krishna, rain, night). It draws a mukhda and an antara from the same theme. The offline song factory uses it so each language has varied lyrics with no model call.

## physics.py — Box2D feel
Backend: `import Box2D` (pybox2d 2.3.10, the C++ engine). If that fails (a laptop without the wheel) a small pure-Python solver ports the same algorithms. `BACKEND` says which ran and is written into every score.

| Effect | Model | Result |
|---|---|---|
| **rubato** | A heavy body on a damped spring (k 14, damping ratio 0.3). Long phrase-ending notes kick it; it swings back. | Note onsets move by a few ms (limit 28 ms), so phrases lean into their ends and recover. |
| **weight** | A ball dropped onto a floor that follows the melody. | Leaps hit harder than steps, so velocity runs 0.62 to 1.0; stressed notes (vadi and samvadi) add 0.06. |
| **meend** | A critically damped spring; a bigger interval is a heavier mass. | The settling time is the glide time (up to 0.30 s, never more than half the note). |
| **drift** | A spring pushed by small random impulses. | A few cents of vibrato-like wander; auto-tune then removes part of it. |

`humanise(events, beat, seed, stress_notes, sa, guard_from)` applies all four; notes at or after `guard_from` (the tihai) keep exact timing so the last note stays on sam.

## gan.py — phrase GAN
A tiny generative adversarial network: the **generator** maps 6 noise values to 8 melodic contour values (6 -> 16 -> 8), the **discriminator** maps a contour to a realness score (8 -> 16 -> 1). It is trained offline with numpy (`agentic/train_gan.py`) on 8-note phrases harvested from the grammar across all classical ragas; the weights ship as `gan_weights.json`. Inference is plain Python so it runs in the Lambda.
At composition time a generated contour is **snapped to the raga's own notes**, so it can never leave the raga, and a phrase the discriminator scores below 0.35 is thrown away (up to six tries). Honest limit: it varies phrases in the style of the grammar; it does not learn taste.

## autotune.py — pull to the shruti
`snap(f, sa, scale, speed)` moves a pitch a fraction `speed` of the way (in log frequency) to the nearest allowed svara. `speed` 1.0 is the hard robotic snap, 0.3 is gentle. `track()` does the same for a recorded pitch track and leaves notes inside a dead-band alone so vibrato survives. `score()` retunes every lead note (default speed 0.75) and returns the mean correction in cents. The tihai uses speed 1.0 so the final Sa is exact.

## agentic/ — the offline song factory
`evolve.py` (producer agents, Thompson sampling, catalogue), `critics.py` (eight rule-based critics), `library.py` (reference-tune profiles), `make_poems.py`, `train_gan.py`. See [AGENTIC_ARCHITECTURE.md](AGENTIC_ARCHITECTURE.md) and [the agents page](../tool_layer_mhraga/mhraaga-cloud/web/docs/agents.html).

## Tests
`tests/test_engine_api.py` (grammar, scores land on sam for every tala), `tests/test_physics_team.py` (physics, auto-tune, GAN, backend), `tests/test_agentic.py`, `tests/test_poems.py`, `tests/test_studio.py`, `tests/test_voice.py`, `tests/test_admin.py` (the dashboard). Run with `python3 tests/test_*.py`; use `PYTHONPATH=/tmp/b2d /usr/bin/python3 ...` to run against the real Box2D build.
