# mhRaaga API (for developers)

Base URL: `https://www.mhraaga.in/api` (the same API the website and the Android app use). JSON in, JSON out.

## Read this first
- **There are no API keys.** Access is by user account. Create an account, sign in, and send the token. Each account has its own
  quota (30 songs per day), so one developer cannot spend another's.
- **Call it from a server, a script or the app, not from another website's JavaScript.** The API sends no CORS headers
  (`connect-src 'self'`), so a browser page on another domain is blocked. A backend or mobile client works.
- **Be gentle.** The API is throttled (about 20 requests per second overall, 2 per second on sign-in). Eight wrong passwords lock an account
  for 10 minutes. Use one account per integration and keep the token (it is valid 7 days).
- Songs are created by a hosted language model plus a rule-based composer. It costs money per song, which is why there is a daily cap.

## Quick start
```bash
B=https://www.mhraaga.in/api
# 1. create an account (once), or log in
TOKEN=$(curl -s $B/auth/signup -H 'Content-Type: application/json' \
  -d '{"name":"My App","email":"me@example.com","password":"a-long-password"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
# TOKEN=$(curl -s $B/auth/login -d '{"email":"me@example.com","password":"a-long-password"}' ...)

# 2. compose a song
curl -s $B/compose -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"prompt":"a calm morning bhajan to Krishna","language":"hindi","duration":120}' > song.json

# 3. the score is in song.json (notes, tabla, lyrics); render it with web/synth.js (Web Audio) or lib/synth.dart (Dart)
```

## Endpoints
`Auth` = send `Authorization: Bearer <token>`.

| Method and path | Auth | What it does |
|---|---|---|
| `GET /health` | no | Liveness check and the list of talas. |
| `POST /auth/signup` | no | `{name, email, password(8-128)}` -> `201 {token, user}`. `409` if the email exists. |
| `POST /auth/login` | no | `{email, password}` -> `{token, user}`. `401` wrong, `429` locked. |
| `GET /me` | yes | Name, email, role, `composed_today`, `daily_limit`. |
| `PATCH /me` | yes | `{name}` change your display name. |
| `GET /ragas` | no | The raga catalogue (classical, 72 melakartas, gopi 1-16000). |
| `GET /ragas/{name}` | no | One raga: aroha, avaroha, vadi, samvadi, time, mood. |
| `GET /playlist` | no | The community playlist (summaries). |
| `GET /playlist/{id}` | no | A playlist song with its full score. |
| `POST /playlist/{id}/play` or `/download` | no | Counts a play or download. |
| `POST /compose` | yes | Make a song (see below). Counts against the daily limit. |
| `GET /songs` | yes | Your songs (latest 100, summaries). |
| `GET /songs/{id}` | yes | One of your songs with the full score. |
| `DELETE /songs/{id}` | yes | Delete one of your songs. |
| `POST /translate` | yes | `{text, to}` -> `{text, to}`. |
| `POST /tts` | yes | Neural speech: `{text(<=320 chars), lang, style, voice}` -> `{url, seconds, cached}`. `url` is a WAV on the site. |
| `GET /tts/info` | no | Voices, styles and the character limit. |
| `GET/POST /teams`, `/teams/{id}/...` | yes | Shared studio projects: members, layers, comments, assemble, render. |
| `GET/POST /films`, `/film/plan`, `/story/outline`, `/story/section`, `/people` | yes | Film, story and voice-profile tools. |

### Admin endpoints (administrators only)
`GET /admin/users`, `POST /admin/users`, `PATCH /admin/users/{email}` (name, role, disabled, daily_limit, password, reset_quota, extra), `POST /admin/users/{email}/delete`, `GET|PUT /admin/schema`, `GET /admin/stats`, `GET /admin/costs`. `PATCH /me {name}` renames yourself. See [ADMIN.md](ADMIN.md).

### `POST /compose` body
| Field | Type | Notes |
|---|---|---|
| `prompt` | string, 3-800 chars | Required. The mood or idea, in any language. |
| `lyrics` | string, <=3000 | Optional. Your own words; otherwise the model writes them. |
| `language` | string | hindi, marathi, english, telugu, gujarati, kannada, tamil. |
| `raga`, `tala` | string | Optional; otherwise chosen from the prompt. |
| `lead` | `bansuri` / `harmonium` / `veena` | The lead instrument. |
| `tempo` | 40-180 | Beats per minute. |
| `duration` | seconds | Default 90 (150 for a poem). |
| `poem`, `instrumental` | bool | A spoken poem over the raga, or no words. |
| `tonic` | 183, 233 or 234 | The tonic in Hz. |
| `title` | string, <=60 | Optional. |

Response: song summary (`id, title, raga, tala, tempo, mood, language, duration, created, source, prompt`), `brief`, and `score`.

### The score
```
score.sa, score.duration, score.lead_voice ("bansuri"|"harmonium"|"veena")
score.drone   {sa, second, low_sa, pluck}            the tanpura
score.lead    [[t, hz, dur, ornament, velocity, glide], ...]   ornament 0 none, 1 meend, 2 kan
score.tabla   [[t, bol, "left"|"right"|"both", volume], ...]
score.lyrics  [{t, dur, text, tag}, ...]
score.sections [{name: alap|gat|tihai, t0, t1}]
score.meta    raga, tala, tempo, mood, physics (engine, autotune), ...
```
A score is plain JSON, so you can render it yourself. `web/synth.js` (Web Audio) and `mhraaga-app/lib/synth.dart` are reference renderers.

### Errors
`{"error": "message"}` with `400` bad input, `401` no or bad token, `403` not allowed, `404` unknown, `409` exists, `429` limit reached,
`502/503` the language or voice service is busy (retry after a moment).

## Self-hosting
The whole stack is one CloudFormation template plus `infra/deploy.sh` (see [DOMAIN.md](DOMAIN.md) and the root README). If you need high
volume or browser-side access from your own domain, deploy your own copy, and add CORS to your API Gateway.
