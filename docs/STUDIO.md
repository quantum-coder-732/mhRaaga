# Studio features and what was not integrated

Built into the site and API: spoken poems, stories / pravachan / explainers (1 to 30 minutes, written section by section by the model, narrated by the device's voices over a raga bed),
People (consent, voice samples, speaking-style notes learned from pasted transcripts), AI rules in S3 (`rules/ethics.json`, editable by an administrator, versioned in `rules/history/`),
and the self-learning loop (`rules/learned.json` feeds default tāla, tempo and instrument per language). The Android app has songs, poems and speech; stories, People and Studio are web-only for now.

Not copied into this project, on purpose:
- **VoiceStudio** (debpalash/voicestudio) is AGPL-3.0 and needs local GPU models. Embedding it in a hosted service would put this whole service under AGPL. Run it separately on your own machine with the exported samples.
- **Explainroo, VUZA and agnes-video-generator** (MIT) are local Python/Node pipelines that render video with local models and ffmpeg. They do not run in Lambda. The site's Explainer produces the script and on-screen points and plays them; making an exported MP4 needs one of these on a machine with ffmpeg and a speech model. VUZA's Pinterest scraping is a terms-of-service risk and was not used.
- **YouTube links**: the site does not download or transcribe videos. Paste a transcript (Show transcript) into a person's profile and it learns the style from that text. Links you add are kept as notes only.
- **Voice cloning and cloned-voice songs or videos**: the browser and phone cannot do it, and nothing here clones a voice. Samples are stored (privately, with consent) for a local cloning tool.
- **Exported video / MP3 of narration**: the browser cannot record its own speech voices, so narrated stories are played, not downloaded.
