# Physics, auto-tune, GAN phrases and the shared studio

## Song engine (music_engine_framework_layer/mhraaga_engine)

`compose()` builds the raga score from grammar (alap, gat, tihai), then three stages shape it:

1. **GAN phrases** (`gan.py`). A small generative adversarial network (generator 6-16-8, discriminator 8-16-1) trained on about 1,800 eight-note phrases harvested from the grammar of every classical raga, a sample of melakartas and gopi ragas (`agentic/train_gan.py`, numpy, offline). Weights ship in `gan_weights.json`; inference is plain Python so the Lambda needs no numpy. About 30% of gat phrases come from the generator, snapped to the raga's own notes so they cannot leave the raga.
   *Honest limit:* it learns the grammar's phrase shapes, not taste. After training the discriminator scores real and generated phrases about equally (0.5), so its score is a weak filter, not a quality judge.
2. **Physics** (`physics.py`). Runs on the **real Box2D engine** (pybox2d 2.3.10, the C++ library) wherever it can be imported, which is the deployed Lambda (python3.12, x86_64; the wheel is fetched by `deploy.sh`). It drives: *rubato* (a body on a Box2D wheel-joint spring, kicked by phrase endings and sampled at the next note; at most 28 ms, about 10 ms in practice), *weight* (a ball dropped under gravity onto an edge fixture with restitution; the speed at impact sets the dynamic, so leaps strike harder, and stressed vadi/samvadi notes are heavier), *meend glide time* (a critically damped spring whose mass grows with the interval, 0.15 to 0.25 s) and a slow *pitch wander*.
   If Box2D cannot be imported (a laptop without the wheel) the same models run on a small pure-Python solver using the same algorithms; the two agree to about 1 ms. Every score records which one ran in `meta.physics.engine`. The tihai is never moved, so the last note lands exactly on sam.
3. **Auto-tune** (`autotune.py`). Pulls every lead note toward the nearest in-raga shruti (just intonation) by 75%, and hard-snaps the tihai. It also offers `track()` for a recorded pitch track with a dead-band that keeps vibrato.

Notes are now `[time, hz, duration, ornament, velocity, glide]`. Old four-field scores still play. `compose(..., human=False)` turns physics off. The score's `meta.physics` reports what was applied. The web synth, the offline MP3 export and the Android synth all read velocity.

## Shared studio (api/team.py, web/team.html, web/team.js)

One film or song project, up to 150 people and 300 layers. A layer is one film shot or one song section, owned by one artist.

| Role | Can |
|------|-----|
| director | everything: add or remove people, reorder, approve, render, delete the project |
| artist | create (up to 8) and edit only their own layers, set them to review, comment |
| viewer | read and comment |

* **Conflicts:** every layer save carries the revision it was based on. If someone changed the layer first the save fails with 409 and the editor reloads their version. Nobody overwrites anyone silently.
* **Live updates:** the page polls every 5 seconds while visible and only fetches layers changed since the last poll.
* **Film:** "Open assembled film" merges approved layers (or all, if none are approved) in order, saves a copy to your films and opens it in the Film studio.
* **Song:** "Render song" merges the section lyrics and runs the normal composer into the director's library.
* **Storage:** the songs table, partition `team#<id>` (project, layers, comments) plus `member#<email>` index rows.
* **Limits to know:** polling, not websockets, so changes appear within about 5 seconds, not instantly. There is no per-frame or multi-user simultaneous canvas editing; the unit of work is the layer. Invited people must sign up with the same email. There is no email invitation yet.
