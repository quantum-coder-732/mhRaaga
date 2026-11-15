"""Register the Kalkee music agent into Kalkee through its API (needs an Kalkee Admin login).
   AK_EMAIL=... AK_PASSWORD=... AGENT_WEBHOOK_KEY=... RAAGA_URL=https://<raaga host> python -m scripts.register_agent
Kalkee keeps the registry in memory: re-run this after Kalkee restarts. 409 = already registered."""
import os, sys
import httpx

base = os.getenv("AKANADE_AUTH_URL", "https://akanade.algoanalytics.com").rstrip("/")
tok = httpx.post(f"{base}/api/auth/login", json={"email": os.environ["AK_EMAIL"], "password": os.environ["AK_PASSWORD"]}).json()["access_token"]
hook = f"{os.environ['RAAGA_URL'].rstrip('/')}/agent/compose?key={os.environ['AGENT_WEBHOOK_KEY']}"
r = httpx.post(f"{base}/chatbot/api/v1/agents/register", headers={"Authorization": f"Bearer {tok}"}, timeout=30, json={
    "agent_id": "pecova-music-agent", "name": "Kalkee Music Agent",
    "description": "Turns a text prompt into a music brief (raga, taal, mood, instruments, lyrics) for songs and ragas; the Algo Raaga app renders it.",
    "webhook_url": hook, "capabilities": ["music_generation", "lyrics_generation"], "model": "z-ai/glm-5.3-flash",
    "cost_per_call_usd": 0.0002, "latency_p50_ms": 3000, "latency_p95_ms": 9000, "reliability_score": 0.7})
print(r.status_code, r.text[:200])
sys.exit(0 if r.status_code in (201, 409) else 1)
