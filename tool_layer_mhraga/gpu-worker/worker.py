"""AI singer worker: runs on a GPU machine, takes queued jobs from the mhRaaga queue, makes the song with YuE2 and uploads the MP3.

  python worker.py                 loop forever (a GPU with 24 GB memory, Python 3.12, YuE2 installed; see README.md)
  python worker.py --once          do at most one job, then exit
  python worker.py --fake          no GPU: write a short test tone instead of calling YuE2 (checks the queue and the upload only)

It needs AWS credentials (an instance role is best) that can: Query/UpdateItem/PutItem on the mhraaga-songs table, PutObject on
s3://<site bucket>/yue/*. Nothing here talks to the public API. The heartbeat row tells the dashboard that a worker is alive."""
from __future__ import annotations

import argparse
import io
import math
import os
import struct
import subprocess
import tempfile
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key

TABLE = os.environ.get("SONGS_TABLE", "mhraaga-songs")
BUCKET = os.environ.get("SITE_BUCKET", "")
REGION = os.environ.get("AWS_REGION", "ap-south-1")
OWNER = "job#yue"
MODEL = os.environ.get("YUE_MODEL", "m-a-p/YuE2-3B")
NAME = os.environ.get("WORKER_NAME", os.uname().nodename)

_db = boto3.resource("dynamodb", region_name=REGION)
songs = _db.Table(TABLE)
s3 = boto3.client("s3", region_name=REGION)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def heartbeat() -> None:
    songs.put_item(Item={"owner": OWNER, "id": "0worker", "seen": int(time.time()), "name": NAME, "model": MODEL})


def claim() -> dict | None:
    """Take the oldest queued job. The conditional update makes two workers unable to take the same one."""
    r = songs.query(KeyConditionExpression=Key("owner").eq(OWNER), ScanIndexForward=True, Limit=50)
    for it in r.get("Items", []):
        if it["id"] == "0worker" or it.get("status") != "queued":
            continue
        try:
            songs.update_item(Key={"owner": OWNER, "id": it["id"]}, UpdateExpression="SET #s=:r, started=:t, worker=:w", ConditionExpression="#s = :q",
                              ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":r": "running", ":q": "queued", ":t": now(), ":w": NAME})
            return it
        except songs.meta.client.exceptions.ConditionalCheckFailedException:
            continue
    return None


def fake_audio(path: Path, seconds: float = 3.0) -> float:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * 233 * i / 24000))) for i in range(int(24000 * seconds))))
    return seconds


def run_yue(style: str, lyrics: str, out: Path, seed: int | None) -> float:
    from yue2 import YuE2Pipeline  # noqa: PLC0415  (installed on the GPU machine only)
    with YuE2Pipeline.from_pretrained(MODEL, device="cuda") as pipe:
        song = pipe(style=style, lyrics=lyrics, cot="full", seed=seed or 42)
        song.save_artifacts(str(out))
    flac = next(out.glob("audio.*"))
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(flac)], capture_output=True, text=True).stdout.strip() or 0)


def do(job: dict, fake: bool) -> None:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        if fake:
            src, secs = td / "audio.wav", fake_audio(td / "audio.wav")
        else:
            secs = run_yue(job["style"], job["lyrics"], td / "out", int(job["id"]) % 100000)
            src = next((td / "out").glob("audio.*"))
        mp3 = td / "song.mp3"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-codec:a", "libmp3lame", "-b:a", "192k", str(mp3)], check=True)
        key = f"yue/{job['id']}.mp3"
        s3.put_object(Bucket=BUCKET, Key=key, Body=mp3.read_bytes(), ContentType="audio/mpeg", CacheControl="public,max-age=31536000,immutable")
    songs.update_item(Key={"owner": OWNER, "id": job["id"]}, UpdateExpression="SET #s=:d, finished=:t, audio=:a, seconds=:x",
                      ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":d": "done", ":t": now(), ":a": "/" + key, ":x": int(secs)})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true"); ap.add_argument("--fake", action="store_true")
    a = ap.parse_args()
    if not BUCKET:
        raise SystemExit("Set SITE_BUCKET to the site bucket name.")
    while True:
        heartbeat()
        job = claim()
        if job:
            print(f"[{now()}] job {job['id']}: {job['style'][:60]}")
            try:
                do(job, a.fake)
                print("  done")
            except Exception as e:  # noqa: BLE001
                print("  failed:", e)
                songs.update_item(Key={"owner": OWNER, "id": job["id"]}, UpdateExpression="SET #s=:f, error=:e, finished=:t", ExpressionAttributeNames={"#s": "status"},
                                  ExpressionAttributeValues={":f": "failed", ":e": str(e)[:300], ":t": now()})
        if a.once:
            return
        if not job:
            time.sleep(15)


if __name__ == "__main__":
    main()
