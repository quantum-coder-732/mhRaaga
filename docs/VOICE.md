# AI voice

Songs, poems, bhajans, stories, pravachan, the Speech tab and film narration use a neural voice: real audio the browser mixes with the music, instead of the device's own speech. The device voice is still there as a fallback and as a choice ("Device voice").

## How it works
1. The browser asks `POST /api/tts {text, lang, style, voice}` for each line (at most 320 characters).
2. The Lambda (`api/voice.py`) looks for the audio in S3 (`tts/<hash>.wav`). A hit is free and shared by every user. A miss calls an OpenRouter audio model with a strict "read this text word for word, add nothing" prompt, wraps the PCM as a 24 kHz WAV, stores it, and returns its URL.
3. The browser (`neural.js`) downloads and decodes the WAV and schedules it with WebAudio: reverb shared with the raga, the music ducked 8 dB under each line, a limiter on the output, no two lines overlapping (a late line is nudged after the previous one; a long line is sped up at most 20%).
4. If anything fails (no key, daily cap, offline, a line that will not generate) that line is spoken by the device voice, so nothing goes silent.
5. Downloaded MP3 and WAV files now include the AI voice, and so does the film WebM export.
6. The Android player does the same natively (`lib/player.dart`): it fetches the lines, plays them on a second player, and ducks the music.

## Models and cost
* Devotional and poem text (`bhajan`, `song`, `poem`, `pravachan`) uses `openai/gpt-audio`, about $0.005 per spoken line. Stories, explainers, the Speech tab and film narration use `openai/gpt-audio-mini`, about $0.0003 per line. If the mini model returns audio far longer than the text should take (it once added extra sentences), the line is redone on the full model.
* The whole build and test of this feature, with retries, cost about $0.51.
* Caps (environment variables, defaults): `TTS_USER_DAILY_USD=0.60` per user per day, `TTS_SITE_DAILY_USD=12` for the whole site per day. Only new generations count; cached lines are free.
* Change models with `TTS_MODEL` and `TTS_MODEL_MINI`. Voices: `male` = onyx, `female` = shimmer.

## Measured quality (not listening)
Each language was spoken, then transcribed back by a separate model call and compared with the original text: Hindi 96%, Marathi 95%, Telugu, Tamil, Gujarati, Kannada and English 100%. The differences are mostly spelling variants, but a human who knows the language should still listen.
Mix of the two sample songs, rendered offline: voice 3 to 6 dB above the ducked music, peak 0.94, no clipped samples, no overlapping lines.

## Limits
* It speaks, it does not sing to the melody. The melody is the raga lead under it.
* It needs the OpenRouter key and costs money per new line. When a daily cap is reached the device voice takes over.
* The upstream service rate-limits bursts; the server retries with backoff and the browser asks for two lines at a time, so a brand-new song takes about 15 to 40 seconds to prepare the first time. Songs in the playlist are prepared ahead.
* Pronunciation of Indic text is good but not perfect, and the model can occasionally add or drop a word.
* The free open-source alternative (Piper) was not used: it has no Gujarati, Kannada or Tamil voice, and its Hindi voice is non-commercial.
