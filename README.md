# mhRaaga

Compose raga music from a sentence. Krishna's sixteen thousand ragas, a tanpura, bansurī (or harmonium / vīṇā) and tabla
rendered in the browser, with speech-to-text for the prompt and lyrics and text-to-speech to recite the words.

```
tool_layer_mhraga/mhraaga-app/     Flutter (Dart) Android app, offline synth, talks to the live API
tool_layer_mhraga/mhraaga-cloud/   web/ (site)  api/ (Lambda)  infra/ (CloudFormation + deploy.sh)  tests/
music_engine_framework_layer/mhraaga_engine/   raga grammar, 72 melakartas, 16,000 gopī ragas, tālas, composer, LLM brief
```

## How a song is made
1. **Brief** - `brief.py` asks OpenRouter (`z-ai/glm-5.3-flash`, fallback `deepseek/deepseek-v4-flash`) for a JSON plan:
   raga, tāla, tempo, mood, language, lead instrument and lyrics. If the model fails, keyword rules still produce a song (`source: fallback`).
2. **Raga** - 30 classical ragas (vādī, samvādī, pakaḍ, time), any of the 72 melakartas, or **gopī 1-16000**: ascent from one melakarta, descent from
   another, one of three tonics (183/233/234 Hz = 732/932/936 ÷ 4), a janya cut, vādī/samvādī a fourth or fifth apart.
   The model has 72x72x3 = 15,552 scale-tonic pairs; ids 1-16000 give **15,947 distinct** ragas (tested), not exactly 16,000.
3. **Score** - `compose.py` follows the classical form: *alap* (drone, free) -> *gat* (tabla enters, each avartan opens with the pakaḍ on sam,
   vādī/samvādī held longer, meend and kan ornaments) -> *tihai* (closing phrase x3 landing exactly on sam). Output is a small JSON score.
4. **Sound** - the browser synthesises it (Web Audio) from physical models: plucked-string tanpura and veena, breathy bansuri, reed harmonium, tabla by its modes, a room reverb, human timing and dynamics. See [docs/SOUND.md](docs/SOUND.md). Piano-roll view, lyrics, seek, MP3/WAV export (with the AI voice).
5. **Voice** - speech-to-text (mic buttons) and text-to-speech use the browser's Web Speech API (Chrome/Edge/Safari). The browser vendor's
   speech service processes the audio. TTS recites the words over the music; it does not pitch syllables to the raga.

## Run it locally (works now)
```bash
python3 tool_layer_mhraga/mhraaga-cloud/api/local_server.py        # http://localhost:8787, same Lambda handler, JSON-file DB
python3 tool_layer_mhraga/mhraaga-cloud/tests/test_engine_api.py   # 9 tests: engine, auth, quota, tokens
```
Put `OPENROUTER_API_KEY=...` in `.env` (gitignored) to use the LLM planner; without it the keyword fallback runs.

## Deploy to AWS (S3 + CloudFront + API Gateway + Lambda + DynamoDB)
```bash
tool_layer_mhraga/mhraaga-cloud/infra/deploy.sh    # AWS profile "mhraaga"; prints the CloudFront URL and writes DEPLOY_URL.txt
```
- **Site**: private S3 bucket behind CloudFront (OAC), HTTPS only, CSP + HSTS + microphone-only Permissions-Policy.
- **API**: HTTP API -> Lambda (Python 3.12, x86_64), reachable only through CloudFront (secret origin header). Throttled routes,
  30 songs per user per day, 8 wrong passwords lock an account for 10 minutes.
- **Data**: DynamoDB `mhraaga-users` (scrypt password hashes) and `mhraaga-songs`, on-demand.
- **Secrets**: OpenRouter key and JWT secret in SSM Parameter Store (SecureString); never in the repo or template.
- **VPC**: the Lambda runs outside a VPC on purpose. In a VPC it would need a NAT gateway (~$32/month) to reach OpenRouter, which contradicts "free for now".

### Status
**Live: https://d1bka1wc4jd8uy.cloudfront.net** (account 877157050453, ap-south-1, stack `mhraaga`).
Tested through CloudFront: site and assets load, signup, login (wrong password rejected), compose with GLM-5.3-flash, list, fetch, delete,
unauthenticated compose returns 401, and the raw API Gateway URL returns 403.
The first account supplied (052005814894) could not be used: an AWS Organizations service control policy denies Lambda, S3, DynamoDB and more there.
Deploy with `AWS_PROFILE=default infra/deploy.sh`. To tear everything down: empty the `mhraaga-site-*` bucket, then `aws cloudformation delete-stack --stack-name mhraaga`.

### Site pages
`index.html` landing, `ragas.html` raga atlas (classical, 72 melakartas, gopī 1-16000, with a Listen button), `login.html` sign in / create account,
`app.html` composer plus the **Community playlist** (6 songs, readable without login via `GET /playlist`). Composing needs a login.
Sign-up is open; accounts are created on the login page. Change any shared or seeded password after first use.

### Android app (Flutter / Dart)
`tool_layer_mhraga/mhraaga-app`: Playlist, My songs, Compose (mic dictation) and Ragas tabs, a now-playing screen with piano roll and
lyrics, and a Dart port of the synth that renders the score to a WAV on the phone. It uses the same CloudFront API.
```bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 ANDROID_HOME=$HOME/android-sdk PATH=$HOME/flutter/bin:$PATH
cd tool_layer_mhraga/mhraaga-app && flutter build apk --release
cp build/app/outputs/flutter-apk/app-release.apk ../mhraaga-cloud/web/mhraaga.apk
AWS_PROFILE=default ../mhraaga-cloud/infra/deploy.sh      # publishes it at /mhraaga.apk
```
Download: https://d1bka1wc4jd8uy.cloudfront.net/mhraaga.apk (allow installs from your browser). The APK is signed with a local key
(`~/.mhraaga-keys/release.jks`, referenced by the git-ignored `android/key.properties`); keep that file, or updates will not install over it.
Not tested on a physical phone yet: speech-to-text depends on the device's speech service.

## Agentic song factory (new)
Producer agents (raga, tāla, tempo, lead, theme, tonic) pick options by Thompson sampling, a composer renders the song, seven critics review it
(raga rules, cadence on sam, phrase variety, contour, rhythm, lyric script and pacing, similarity to the reference tunes in `~/library`), and
Kalkee's Shapley module splits the reward across the agents so each one learns which choices work. The catalog holds at most 100 generated songs
(about 14 each in Hindi, Marathi, English, Telugu, Gujarati, Kannada and Tamil); better songs replace the weakest, and weak ones are re-composed.
Songs go to S3 `catalog/`, the 14 reference tunes to S3 `library/` (shown on the landing page), and the shared playlist is synced.
First runs lifted the mean critic reward from 0.862 to 0.969. The critics are rule-based, not listeners. Details and limits: [docs/AGENTIC_ARCHITECTURE.md](docs/AGENTIC_ARCHITECTURE.md).

### Look and Krishna flute style
The site uses a Suno-style sidebar layout with song rows, thumbnails and style tags. “Krishna flute” is a tag on the Create page: it silently picks one of the 16,000 gopī ragas (the number and the Hz values are not shown) and sets the bansurī.

### Speech tab (translate, speak, dictate)
Create has Songs and Speech tabs (Simple / Advanced like Suno). Speech: type, dictate (21 input languages incl. Indian and foreign), translate with the language model
(`POST /translate`, sign-in required), choose tone, vocal gender (a best guess from voice names), an Indian or foreign voice, and an optional raga bed under the voice.
"Test the voices" plays a greeting in every voice the device has. It uses the browser's or phone's own speech engines, so the voices available differ per device.
YouTube: there is no downloader. Paste a transcript (YouTube's “Show transcript”) or your own text and translate it.

### Studio: poems, stories, pravachan, people, rules, domain
Spoken poems (tag on Create), Stories / Pravachan / Explainer (1 to 30 min), People (voice samples with consent, style learned from pasted transcripts), and Studio (live AI rules in S3, learned defaults).
What is built and what is deliberately not: [docs/STUDIO.md](docs/STUDIO.md). Using mhraaga.in: [docs/DOMAIN.md](docs/DOMAIN.md).

### Downloads, counters, media tools
The site exports **MP3** (lamejs, vendored as `web/lame.min.js`) and **WAV** in the browser. Shared-playlist songs count plays and downloads
(`POST /api/playlist/{id}/play|download`, stored in DynamoDB, shown in the list and the app). `tool_layer_mhraga/tools/mediakit.py` converts
audio and video locally with ffmpeg (mp3/wav/mp4 with a waveform video). Speech-to-text and text-to-speech are the browser's/phone's own services.
Not built, on purpose: a YouTube downloader or converter. It breaks YouTube's terms and copies other people's recordings.

## Secrets
`.env` and `build/` are gitignored. The keys used during development were pasted into a chat: rotate the AWS key, OpenRouter key and GitHub token.

## Documentation
All docs are in [docs/](docs/README.md), including the detailed [architecture](docs/ARCHITECTURE.md) and the Kalkee documents. For developers: [docs/API.md](docs/API.md) and the architecture page at https://www.mhraaga.in/developers.html.
