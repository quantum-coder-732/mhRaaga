#!/usr/bin/env bash
# Run ON the Akanade EC2 (needs docker). Pulls the repo, builds, and (re)starts aRaaga on :9100.
# Data (accounts/tracks JSON or DynamoDB) and audio live in S3 / the 'raaga-data' volume. Login = Akanade's login.
set -euo pipefail
cd "$(dirname "$0")"
docker build -t algo-raaga .
docker rm -f algo-raaga 2>/dev/null || true
ENVF=/opt/algo-raaga/raaga.env; [ -f "$ENVF" ] || ENVF=   # secrets (AGENT_WEBHOOK_KEY, OPENROUTER_API_KEY), mode 600, never in git
docker run -d --name algo-raaga ${ENVF:+--env-file $ENVF} --restart unless-stopped -p 127.0.0.1:9100:9100 -v raaga-data:/data \
  -e AKANADE_AUTH_URL="${AKANADE_AUTH_URL:-https://akanade.algoanalytics.com}" \
  -e MUSIC_S3_BUCKET=algo-raaga-877157050453 -e AWS_REGION=ap-south-1 \
  -e MUSIC_ADMINS="${MUSIC_ADMINS:-}" algo-raaga   # AWS creds come from the instance role
curl -fs localhost:9100/api/health && echo " <- aRaaga up"
