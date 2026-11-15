"""Settings from environment (all optional; defaults work for local dev)."""
import os
from pathlib import Path

DATA_DIR = Path(os.getenv("MUSIC_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
AUDIO_DIR = DATA_DIR / "audio"
# DynamoDB: set DYNAMO_ENDPOINT (e.g. http://localhost:8002 for dynamodb-local). Empty -> JSON file store.
DYNAMO_ENDPOINT = os.getenv("DYNAMO_ENDPOINT", "")
DYNAMO_REGION = os.getenv("AWS_REGION", "ap-south-1")
TABLE_PREFIX = os.getenv("MUSIC_TABLE_PREFIX", "algo_music_")
# The Kalkee AI platform that hosts the Kalkee music agent (OpenRouter / SLM routing).
AKANADE_URL = os.getenv("AKANADE_URL", "https://akanade.algoanalytics.com/chatbot").rstrip("/")
AKANADE_TOKEN = os.getenv("AKANADE_TOKEN", "")
AKANADE_TIMEOUT = float(os.getenv("AKANADE_TIMEOUT", "40"))
SEED_SAMPLES = os.getenv("MUSIC_SEED_SAMPLES", "1") == "1"
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
# Accounts live in this service. MUSIC_JWT_SECRET signs session tokens (a random one is persisted under DATA_DIR if unset).
JWT_SECRET = os.getenv("MUSIC_JWT_SECRET", "")
TOKEN_DAYS = int(os.getenv("MUSIC_TOKEN_DAYS", "30"))
# Local dev/tests only: trust the X-User-Id header when no bearer token is sent.
ALLOW_GUEST = os.getenv("MUSIC_ALLOW_GUEST", "0") == "1"
# Audio lives in S3 (source of truth); the local data/ dir is just a cache. Empty bucket -> local-only.
S3_BUCKET = os.getenv("MUSIC_S3_BUCKET", "algo-raaga-877157050453")
S3_REGION = os.getenv("MUSIC_S3_REGION", "ap-south-1")
# Spoken/sung-style vocal layer via Amazon Polly (in your own AWS account). "0" disables it.
VOICE_ENABLED = os.getenv("MUSIC_VOICE", "1") == "1"
LIBRARY_DIR = DATA_DIR / "library"
# Single sign-on: the same email + password as Kalkee. Raaga asks Kalkee's /api/auth/login first and only
# falls back to its own accounts if Kalkee says no (or is unreachable). Empty disables.
AKANADE_AUTH_URL = os.getenv("AKANADE_AUTH_URL", "https://akanade.algoanalytics.com").rstrip("/")
# Admins/senior managers who may see per-song costs: emails here, or anyone Kalkee reports as Admin/Executive.
ADMINS = {e.strip().lower() for e in os.getenv("MUSIC_ADMINS", "").split(",") if e.strip()}
ADMIN_ROLES = {"admin", "manager2", "executive"}  # Kalkee: Admin, Senior Manager (Manager2)
# Unit prices in USD (ap-south-1 list prices; override with env as AWS prices change). All figures are estimates.
PRICE_POLLY_NEURAL_PER_M_CHARS = float(os.getenv("PRICE_VOICE_PER_M_CHARS", "0"))  # Kalkee TTS (Piper) is free
PRICE_LLM_IN_PER_M_TOKENS = float(os.getenv("PRICE_LLM_IN_PER_M", "0.5"))
PRICE_LLM_OUT_PER_M_TOKENS = float(os.getenv("PRICE_LLM_OUT_PER_M", "1.5"))
PRICE_EC2_PER_HOUR = float(os.getenv("PRICE_EC2_PER_HOUR", "0.0448"))      # t3.medium
PRICE_S3_PER_GB_MONTH = float(os.getenv("PRICE_S3_PER_GB_MONTH", "0.025"))
PRICE_CDN_PER_GB = float(os.getenv("PRICE_CDN_PER_GB", "0.109"))           # CloudFront egress, India
# Optional: an OpenRouter *management* key lets the admin cost page show total account credits vs. this app's share.
OPENROUTER_MANAGEMENT_KEY = os.getenv("OPENROUTER_MANAGEMENT_KEY", "")
# The music agent (registered into Kalkee via POST /api/v1/agents/register) calls OpenRouter with the cheapest capable model.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
AGENT_MODELS = [m for m in os.getenv("MUSIC_AGENT_MODELS", "z-ai/glm-5.3-flash,qwen/qwen3.7-flash").split(",") if m]
AGENT_WEBHOOK_KEY = os.getenv("AGENT_WEBHOOK_KEY", "")
# Kalkee's named managers see costs too (same list Kalkee uses).
ADMIN_NAMES = {n.strip().casefold() for n in os.getenv("MUSIC_ADMIN_NAMES", "Nikhil Wate,Aniruddha Pant").split(",") if n.strip()}
