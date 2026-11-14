# aRaaga service

FastAPI service behind the aRaaga web and mobile apps: generation jobs, tracks,
discovery (trending/new/top/search), likes, plays and range-capable audio streaming.

- **AI platform:** the prompt goes to Akanade's `pecova-music-agent`
  (`Algo-aKANADE/.../app/framework/agents/music_agent.py`, routed over OpenRouter or SLM),
  which returns a *brief* (raga, taal, mood, instruments, lyrics). Without `AKANADE_TOKEN`
  or when Akanade is down, a keyword fallback is used (`brief_source` on a track says which).
- **Rendering:** `app/engine.py`, an offline numpy synthesizer (raga scales, tanpura, taal-driven
  tabla, flute/sitar/harmonium/piano). It is not a neural model and does not sing; lyrics are text.
- **Storage:** DynamoDB when `DYNAMO_ENDPOINT` is set (tables are auto-created), else a JSON file.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
docker run -d -p 8002:8000 amazon/dynamodb-local -jar DynamoDBLocal.jar -sharedDb -inMemory   # optional
DYNAMO_ENDPOINT=http://localhost:8002 AKANADE_URL=http://localhost:8001 AKANADE_TOKEN=<jwt> \
  .venv/bin/uvicorn app.main:app --port 9100
.venv/bin/python -m pytest
```

Needs `ffmpeg` for mp3 (WAV is served if it is missing). Accounts are email + password (`/api/auth/signup`, `/login`, `/me`); every music route needs the bearer token. On first start six sample tracks are rendered.
