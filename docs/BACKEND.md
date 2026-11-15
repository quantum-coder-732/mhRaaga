# The backend, file by file

Folder: `tool_layer_mhraga/mhraaga-cloud/api/`. One Lambda (Python 3.12, x86_64) behind API Gateway. Standard library plus boto3 only; the Box2D wheel is added at deploy time.
`local_server.py` runs the same handler on your laptop with a JSON-file database (`python3 api/local_server.py`, http://localhost:8787).

## handler.py — the front door
`handler(event)` routes by method and path under `/api`, turns `ApiError` into `{"error": ...}`, and never leaks internals (an unexpected error is logged and returns a plain 500).

| Concern | How |
|---|---|
| **Access** | If `ORIGIN_SECRET` is set, the `x-origin-verify` header must match it (CloudFront adds it), so the raw API Gateway address answers 403. |
| **Accounts** | `signup` and `login`. Passwords are hashed with scrypt (n=2^14, r=8, p=1, random 16-byte salt). A token is a 7-day HS256-signed JWT with the email as subject. Eight wrong passwords lock an account for 10 minutes. A disabled account cannot sign in and its tokens stop working. |
| **Quota** | `take_quota` allows 30 songs per user per day (`DAILY_COMPOSE_LIMIT`), or the user's own `limit` if an administrator set one. |
| **Compose** | `make_song`: checks the text against the rules (`studio.check`), takes quota, builds the brief, gets the raga, composes the score, saves it, returns it. |
| **Songs** | `list_songs`, `get_song`, `delete_song` (your own); the shared playlist is the owner `playlist#common` and is readable without sign-in. Plays and downloads are counted with an atomic `ADD`. |
| **Other routes** | `/translate`, `/rules`, `/people`, `/story/*`, `/films`, `/film/plan`, `/tts`, `/teams`, `/admin`. |
| **Secrets** | Read from SSM Parameter Store on first use and cached for the life of the container. |

## studio.py — rules, people, stories, films
- **Rules**: `DEFAULT_RULES` (principles, blocked terms, blocked impersonation phrases, maximum prompt length) are kept as `rules/ethics.json` in S3 with a version history. `check(*texts)` runs on **every** prompt, lyric, story topic, translation and profile text and returns 422 on a violation. Administrators edit them with `PUT /rules`. `learned_defaults(language)` returns the tala, lead and tempo the offline factory found work best.
- **People**: voice profiles with consent. A profile stores a name, a consent note, up to 20 audio samples (S3 `samples/`, each at most 2.5 MB) and style notes learned from a **pasted transcript** (`people_learn`); nothing is downloaded from anywhere. Profiles are for you or people who agreed, and are never used to clone a voice.
- **Stories and pravachan**: `story_outline` then `story_section` write a long spoken piece (1 to 30 minutes) section by section, limited to 80 model calls per user per day.
- **Films**: `film_plan` expands a short idea into a director's brief and a storyboard of scenes with effects (glow, vignette, grain, blur, light leak, particles, slow zoom, fade, black and white, warm, cool) using two model calls. `film_save/get/delete` keep projects up to 330 KB.

## team.py — shared studio
Up to 150 members and 300 layers per project, all stored in the songs table:

| Key (owner / id) | Meaning |
|---|---|
| `team#<pid>` / `0meta` | Project: title, kind (film or song), members `{email: role}`, revision |
| `team#<pid>` / `L#<lid>` | A layer (a film shot or a song section) owned by one artist |
| `team#<pid>` / `C#<ts>-<r>` | A comment |
| `member#<email>` / `<pid>` | Index so a member can list their projects |

Roles: **director** (everything), **artist** (their own layers), **viewer** (read and comment). Layer saves carry the revision they were based on and lose with **409** if someone changed the layer first (optimistic locking). Clients poll `GET /teams/{pid}?since=...` every 5 s; only changed layers return. `assemble` orders film scenes or merges song lyrics; `render_song` lets the director turn the merged lyrics into a normal song.

## voice.py — neural speech
`POST /tts {text, lang, style, voice}` -> `{url, seconds, cached}`. Calls OpenRouter's `openai/gpt-audio` (poem, bhajan, song, pravachan) or `gpt-audio-mini` (story, explainer, speech, narration) with a strict "read it word for word, add nothing" prompt. The audio is stored once under `tts/<hash>.wav` (the key is `v2|model|voice|style|lang|text`) so every later request is free and instant. Defences: retry with back-off on 429 and 5xx, a 503 "busy" the client can retry, output that is far too long or too short is rejected, mini output that adds sentences is redone on the full model, and spend is capped at **$0.60 per user and $12 per site per day**. See [VOICE.md](VOICE.md).

## admin.py — the dashboard API
Users, roles, custom columns, usage and cloud cost. See [ADMIN.md](ADMIN.md).

## Data (DynamoDB)
**`mhraaga-users`** (key `email`): `name`, `pw`, `created`, `fails`, `locked_until`, `qday`/`qn` (today's song count), `tday`/`tusd` (today's voice spend), and, set by the dashboard, `role`, `disabled`, `limit`, `extra` (custom columns), `last_login`.
**`mhraaga-songs`** (keys `owner`, `id`): one table for many kinds of rows, told apart by the owner:

| Owner | Holds |
|---|---|
| `<email>` | A user's songs (`brief` and `score` stored as JSON strings) |
| `playlist#common` | The shared community playlist and its counters |
| `people#<email>`, `film#<email>` | Voice profiles, film projects |
| `team#...`, `member#...` | Shared studio (above) |
| `quota#tts` | Site voice spend per day |
| `admin#audit`, `admin#config`, `admin#cache` | Admin action log (kept 180 days), custom column definitions, cached cost report |

## Infrastructure (`infra/`)
`template.yaml` (CloudFormation: S3, CloudFront with a strict CSP, API Gateway with throttling, the Lambda and its least-privilege role, two tables) and `deploy.sh` (builds the zip with the engine and a Box2D wheel, updates the stack, syncs the site, invalidates the cache and checks the raw API returns 403). The Lambda role can read parameters under `/mhraaga/*`, use `rules/`, `samples/` and `tts/` in the site bucket, list `tts/`, scan the users table, and read AWS cost (`ce:GetCostAndUsage`).
