# Sound: why it is meant to sound natural

The first synth used bare oscillators: a sine flute, a sawtooth harmonium, a plain tone for the strings. That is why songs sounded electronic.
Each instrument is now a small physical model (web `web/synth.js`, Android `lib/synth.dart`, same design).

| Instrument | Model |
|---|---|
| Tanpura, veena | Karplus-Strong plucked string: a delay loop with loss, so the attack and the fade of the highs are real; a soft clip stands in for the jawari bridge, bright at first and mellowing as the string quietens. A veena meend is a real slide of the sounding string. |
| Bansuri | A blown tube: strong fundamental, weak overtones, a chiff of air at the start, breath noise through the note, vibrato that begins after the note, slow pitch drift, an unslurred note scooped up into pitch. |
| Harmonium | Reed spectrum, two reed banks slightly out of tune plus an octave bank, uneven bellows pressure, wooden body resonances at 700 and 2100 Hz. |
| Tabla | Dayan: Sa with harmonic partials that decay at different rates, skin slap and rim click. Bayan: a boom whose pitch rises, a wet thud, a muted ka. No two strokes the same. |
| Manjira | Brass cymbals (inharmonic partials), soft, on the beat in devotional songs (web). |
| Room | A stereo impulse response with pre-delay and early reflections, and a tail that darkens as it fades. |
| Master | Soft tape-style saturation, a gentle top-end roll-off, a low shelf, compressor and limiter. |
| Playing | Timing jitter of a few milliseconds, velocity variation, and a dynamic arc: a quiet alap that grows, a gat that swells and settles with each phrase, a strong tihai. |

## Measured (45 s of the same bhajan score, old synth against new, against 5 reference tracks in `~/library`)
| | old | new | reference tracks |
|---|---|---|---|
| 95% of energy below | 345 Hz | 620 Hz | 410 to 880 Hz |
| Spectral flatness (richness) | 0.004 | 0.025 | 0.007 to 0.049 |
| Loudness range, 1 s windows | 3.9 dB | 8 dB | 5 to 16 dB |

These are numbers about timbre and dynamics. The reference recordings were only measured, never copied or sampled.

## Mix balance (measured, 80 s of the bhajan, alap and gat)
Rendering each part alone showed the tanpura 20 dB under the flute, so the drone was almost inaudible. I raised it 10 dB. Now:
the tanpura is about 11 dB under the flute, the tabla about 3 dB under it, and the overall level is unchanged. The flute leads, the drone gives the floor, the tabla keeps time.

## Limits
- These are models, not recordings. They sound far less electronic than before, but a recording of a real player is still better.
  The way to go further is a library of properly licensed instrument samples, or a hosted music model (a GPU service). Neither is included.
- The voice speaks the words; it does not sing them to the melody.
