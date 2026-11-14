# aRaaga: API + web in one container.  Build from this directory:  docker build -t algo-raaga .
FROM node:22-slim AS web
WORKDIR /w
COPY music-web/package*.json ./
RUN npm ci
COPY music-web/ ./
ENV VITE_MUSIC_BASE_URL=
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY music-backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY music-backend/app app
COPY --from=web /w/dist web
ENV MUSIC_DATA_DIR=/data
EXPOSE 9100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9100"]
