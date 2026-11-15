#!/usr/bin/env bash
# aRaaga, all local: DynamoDB-local (docker), the service (:9100) and the web app (:5174).
# Optional: export AKANADE_URL / AKANADE_TOKEN to plan songs with Kalkee music agent.
set -e
cd "$(dirname "$0")"
docker start algo-music-ddb >/dev/null 2>&1 || docker run -d --name algo-music-ddb -p 8002:8000 \
  amazon/dynamodb-local:latest -jar DynamoDBLocal.jar -sharedDb -inMemory >/dev/null
[ -d music-backend/.venv ] || { python3 -m venv music-backend/.venv && music-backend/.venv/bin/pip install -q -r music-backend/requirements.txt; }
[ -d music-web/node_modules ] || (cd music-web && npm install --silent)
(cd music-backend && DYNAMO_ENDPOINT=http://localhost:8002 .venv/bin/uvicorn app.main:app --port 9100) &
trap 'kill 0' EXIT
(cd music-web && npx vite --port 5174) &
echo "aRaaga: http://localhost:5174   API: http://localhost:9100/api/health"
wait
