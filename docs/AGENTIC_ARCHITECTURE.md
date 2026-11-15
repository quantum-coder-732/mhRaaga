# mhRaaga agentic architecture

Songs are made by a small network of agents that learn from automatic feedback. It uses one piece of Kalkee,
the Shapley credit split (see [kalkee/LEARNING.md](kalkee/LEARNING.md)), and re-implements Thompson sampling, on top of the raga engine.
Everything is standard-library Python and runs offline; an LLM is optional.

```
 reference tunes (~/library)            producer agents (Thompson sampling, one Beta posterior per language x agent x arm)
        |  ffmpeg + Goertzel chroma            raga   : classical | gopi 1-16000 | melakarta
        v                                      tala   : teental keherwa dadra rupak jhaptal ektal adi
 library_profiles.json                         tempo  : 54 .. 104 bpm        lead : bansuri harmonium veena
        |                                      theme  : dawn krishna rain night     tonic : 183 / 233 / 234 Hz
        |                                          |
        |                                          v
        |                                 composer (alap -> gat -> tihai) + lyric bank (7 languages)
        |                                          |  score JSON
        v                                          v
   critic agents  <-------------------------------- review(score, brief)
   raga_fidelity  cadence  phrase_variety  contour  rhythm  lyrics_fit  library_affinity
        |  weighted reward R in [0,1]  +  per-critic scores
        v
   quality of each producer = mean of the critics that judge its work
        |
        v
   Kalkee Shapley: R split fairly across producers (efficiency: shares sum to R)
        |
        v
   each producer's Beta(a,b) for the arm it chose += its share  ->  next round samples better arms
        |
        v
   catalog (cap 100, per-language quota 15/15/14x5): better song replaces the weakest of its language;
   the weakest are also re-composed (new seed + one gene re-sampled) and swapped in only if they score higher
        |
        v
   publish_catalog.py -> S3 catalog/ + library/  and  DynamoDB playlist#common  ->  site, API, Android app
```

## Pieces
| File | Role |
|---|---|
| `mhraaga_engine/lyrics_bank.py` | native-script couplets for Hindi, Marathi, English, Telugu, Gujarati, Kannada, Tamil, four themes each |
| `mhraaga_engine/agentic/library.py` | analyses real recordings into pitch-class (tonic-relative) and tempo profiles |
| `mhraaga_engine/agentic/critics.py` | seven critics, each pure and deterministic; `review()` returns scores, details and the weighted reward |
| `mhraaga_engine/agentic/evolve.py` | policy (Thompson), Kalkee credit attribution, catalog with cap and quotas, `run()` |
| `tool_layer_mhraga/mhraaga-cloud/infra/publish_catalog.py` | runs the loop, then pushes songs and library tunes to S3 and syncs the shared playlist |
| `tool_layer_mhraga/mhraaga-cloud/tests/test_agentic.py` | languages, critic ranges, Shapley efficiency, learning curve, cap |

## What the critics check
- **raga_fidelity**: notes inside the raga's scale, vadi given a longer dwell than average, the pakad appearing.
- **cadence**: the song ends on Sa, exactly on a tabla sam beat.
- **phrase_variety**: distinct 4-note phrases, no long repeats.
- **contour**: mostly stepwise motion, a one-to-two octave range, a sensible share of ornaments.
- **rhythm**: lead notes on the beat grid, tabla fill, notes per beat, tempo suited to the tala.
- **lyrics_fit**: lyrics written in the right script for the language, singable letters per second, lines paced across avartans.
- **library_affinity**: cosine similarity of the song's pitch profile to the closest recorded raga in the library, plus tempo closeness.

## Spoken poems (like the reference poem videos)
The reference files in `~/library` (`Sometimes two people`, `What if the one you`, `When messages disappear`, `The Truth of Radha's Love`,
`Loving From Within`, `बिना प्रेम धीरज`) are 2 to 9 minute rhymed spiritual-love poems with soft music, gold italic lines on a purple stage.
A song with `poem: true` (the “Spoken poem” tag) is composed to match: 14 to 18 short rhymed lines, about 150 seconds, a long soft alap with the bansurī
and drone, no tabla, lines spaced evenly across the whole piece, ending on Sa. The `poem_form` critic scores rhyme, line count and length, duration, pacing and the
Sa ending; for poems it replaces the tabla-rhythm critic. `agentic/make_poems.py` writes the poems with the language model (rhyme-gated), `poems.py` serves them offline.
`tests/test_poems.py` checks every language against these rules.

## Result of the first runs
2 runs, 1,224 candidates scored, 136 replacements. Mean critic reward of the catalog rose from 0.862 to 0.969 across 12 rounds.
The learned leaders per language are in `agentic/data/policy.json` and `/catalog/report.json`.

## Limits, said plainly
- The critics are rule-based. They measure raga grammar, rhythm and script, not beauty. A high reward means "obeys the rules and resembles the
  reference tunes", not "a listener loved it". The next critic to add is real listener feedback (plays, likes, skips) fed into the same loop.
- Tempo and tonic estimates from the library recordings are rough (an autocorrelation tempo can be off by 2x; tonic is the strongest pitch class).
- The offline lyric bank is short: 2 couplets per theme per language, combined at random. With an OpenRouter key, the brief planner can write fresh lyrics instead.
- Telugu, Gujarati, Kannada and Tamil lyrics were written without a native-speaker review. Please have them checked before wide release.
- Spoken lyrics depend on the device having a voice for that language; the sung melody does not.

## Run it
```bash
python3 -m mhraaga_engine.agentic.library ~/library                 # (from music_engine_framework_layer) analyse the reference tunes
AWS_PROFILE=default python3 tool_layer_mhraga/mhraaga-cloud/infra/publish_catalog.py --rounds 8   # evolve, then publish
python3 tool_layer_mhraga/mhraaga-cloud/tests/test_agentic.py
```
`deploy.sh` leaves `catalog/` and `library/` alone when it syncs the site.
