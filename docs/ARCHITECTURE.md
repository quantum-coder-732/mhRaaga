# mhRaaga architecture

Live at https://www.mhraaga.in (AWS account 877157050453, region ap-south-1, stack `mhraaga`). A developer-friendly version with a diagram:
https://www.mhraaga.in/developers.html. How to call the API from outside: [API.md](API.md).

## 1. The four layers

```
 ┌────────────────────────────── clients ──────────────────────────────┐
 │ Web app (web/*.js, Web Audio)   Android app (Flutter)   Your server │
 └───────────────┬──────────────────────┬───────────────────────┬──────┘
                 ▼  HTTPS               ▼                       ▼
        ┌────────────────────────────────────────────────────────────┐
        │ CloudFront  www.mhraaga.in / mhraaga.in  (ACM cert, Route53)│
        │   /            -> private S3 site bucket (OAC)              │
        │   /tts/*       -> S3 (cached neural speech, immutable)      │
        │   /api/*       -> API Gateway (throttled), secret header    │
        └───────────────────────────────┬────────────────────────────┘
                                        ▼
        ┌────────────────────────────────────────────────────────────┐
        │ Lambda, Python 3.12, x86_64   api/handler.py                │
        │   engine: compose, ragas, tala, brief, poems, lyrics        │
        │   physics (Box2D), GAN phrases, auto-tune                   │
        │   studio.py (stories, film, rules), team.py, voice.py       │
        └────────┬──────────────────┬───────────────────┬────────────┘
                 ▼                  ▼                   ▼
          DynamoDB            SSM Parameter Store   OpenRouter (hosted models)
          users, songs        keys, JWT, origin     brief, translate, neural voice
```

| Layer | Where | What it does |
|---|---|---|
| Music engine | `music_engine_framework_layer/mhraaga_engine/` | Raga grammar, composer, tala, physics, GAN, auto-tune, lyric banks. Pure Python, no web code. |
| Cloud | `tool_layer_mhraga/mhraaga-cloud/` (`api/`, `web/`, `infra/`, `tests/`) | The Lambda API, the site, CloudFormation and `deploy.sh`. |
| App | `tool_layer_mhraga/mhraaga-app/` | Flutter Android app with a Dart port of the synth. |
| Song factory | `mhraaga_engine/agentic/` | Offline agents that fill the catalogue and learn which choices work. Uses one Kalkee file (see section 6). |

## 2. How a song is made, step by step
1. **Request**: `POST /api/compose` with a prompt (and optional raga, tala, lead, tempo, lyrics, poem, duration). Auth is a JWT (7 days); 30 songs a day per account.
2. **Brief** (`brief.py`): OpenRouter model (`z-ai/glm-5.3-flash`, fallback `deepseek/deepseek-v4-flash`) returns a JSON plan. If it fails, keyword rules still give a plan (`source: fallback`). Learned defaults from the live rules in S3 fill gaps.
3. **Raga** (`ragas.py`): 30 classical ragas, the 72 melakartas, or gopi 1 to 16000 (a pair of melakartas, one of three tonics 183/233/234 Hz, a janya cut). About 15,947 are distinct.
4. **Score** (`compose.py`): alap (drone, free), gat (tabla enters; each avartan opens with the pakad on sam; vadi and samvadi are held; meend and kan ornaments), tihai (a closing phrase three times landing exactly on sam). Lyrics are timed to the phrases.
5. **Feel** (`physics.py`): Box2D (pybox2d 2.3.10; a pure-Python solver if it cannot import). A damped spring gives rubato (note-onset offsets of a few ms), a ball dropped on a melody-shaped floor gives note weight (velocity), a critically damped spring gives the meend time, a small spring wander gives pitch drift.
6. **Phrases** (`gan.py`): a small numpy-trained GAN proposes phrases; a discriminator-style score and the raga rules decide whether to use them.
7. **Auto-tune** (`autotune.py`): pulls pitch toward the shruti of the raga by a fraction; the tihai is snapped fully so the last note lands on Sa.
8. **Result**: a plain JSON score (`sa, drone, lead[t,hz,dur,orn,vel,glide], tabla[t,bol,class,vol], lyrics, sections, meta`) stored in DynamoDB and returned.
9. **Sound** (`web/synth.js`, `mhraaga-app/lib/synth.dart`): rendered on the device from physical models (see [SOUND.md](SOUND.md)).
10. **Voice** (`api/voice.py`, `web/neural.js`): each lyric line goes to `POST /tts`; OpenRouter `openai/gpt-audio` (poems, bhajans, songs, pravachan) or `gpt-audio-mini` (stories, speech, narration) returns audio, stored once in S3 under `tts/<hash>.wav` and shared by all users. The browser mixes it over the music and ducks the music under the voice. Caps: $0.60 per user and $12 per site per day. If it fails, the device voice speaks the line. See [VOICE.md](VOICE.md).

## 3. Data and security
- **DynamoDB** `mhraaga-users` (scrypt hashes, quota, lockout), `mhraaga-songs` (owner + id; the shared playlist is an owner; quota counters for the voice).
- **S3** one private bucket: site files, `catalog/`, `library/`, `rules/`, `samples/`, `tts/`. Sync with `--delete` excludes those data prefixes.
- **SSM** `/mhraaga/openrouter_key`, `jwt_secret`, `origin_secret` as SecureString. Nothing secret is in the repository.
- **CloudFront** adds the origin secret; the raw API Gateway URL returns 403. HSTS, a strict CSP (no inline script or style, `connect-src 'self'`), microphone-only Permissions-Policy.
- **Abuse limits**: route throttling, 8 wrong passwords lock 10 minutes, a content check (`studio.check`) on prompts and lyrics.

## 4. Web app structure
`index.html` (landing and Suno-style shell: sidebar on desktop, bottom bar on phones; views home, create, playlist, mine, stories, people, film, team, studio, ragas), `app.js` (composer and player), `synth.js` (instruments), `neural.js` (voice fetch and mixing), `voice.js` (device voices), `stories.js`, `speech.js`, `film.js` (storyboard and video export), `team.js` (shared studio), `developers.html` (this documentation for developers).

## 5. Shared studio
Up to 150 members and 300 layers per project; roles; optimistic locking; polling. `api/team.py`, `web/team.js`. Details: [TEAM_AND_PHYSICS.md](TEAM_AND_PHYSICS.md).

## 6. Kalkee <a id="kalkee"></a>
**Kalkee (ALGO AKANADE)** is a separate orchestrator product in `orchestrator_framework_layer_kalkee/`: adaptive routing of tasks to agents by Thompson sampling, fair credit across agents with the Shapley value, a reward loop, SLM and PEFT layers. Its documents are in [kalkee/](kalkee/README.md).

**What mhRaaga actually uses from it: one function.** `mhraaga_engine/agentic/evolve.py` loads
`orchestrator_framework_layer_kalkee/orchestrator_framework_layer/akanade/backend/app/framework/shapley.py` (`attribute_reward`) and uses it to split each song's quality score fairly among the producer agents (raga, tala, tempo, lead, theme, tonic, form). If that file is missing, a proportional split is used and the run records `local-fallback`.
- The Thompson-sampling idea is used too, but re-implemented in `evolve.py` (Beta posteriors per agent and choice), not imported.
- **It runs offline** (the song factory that fills the catalogue), not inside the live Lambda. The live API, site and app do not import Kalkee.
- The rest of Kalkee (router, workflow engine, dashboards, PM chatbot, SLM layers) is not part of mhRaaga.

The song factory loop: producer agents pick options -> composer renders a song -> seven rule-based critics (raga fidelity, cadence on sam, phrase variety, contour, rhythm, lyric fit, similarity to reference tunes) score it -> Shapley splits the reward -> each agent updates its posterior. The catalogue keeps at most 100 songs, about 14 per language; better songs replace the weakest. The critics are rules, not listeners. Details: [AGENTIC_ARCHITECTURE.md](AGENTIC_ARCHITECTURE.md).

## 7. Deploy
`DOMAIN_NAME=mhraaga.in CERT_ARN=<arn> AWS_PROFILE=default bash tool_layer_mhraga/mhraaga-cloud/infra/deploy.sh` (about 100 seconds): builds the Lambda zip (handler, engine, a Box2D wheel fetched for x86_64), updates the CloudFormation stack, syncs `web/` to S3, invalidates CloudFront, and checks that the direct API returns 403. Android: `flutter build apk --release`, copy to `web/mhraaga.apk`, deploy.

## 8. Known limits
Instruments are models, not recordings; the voice speaks and does not sing; Indic pronunciation is good but not perfect; composing and speech call paid hosted models and are capped; the API has accounts but no API keys and no CORS; the Android app has not been tested on a physical phone.
