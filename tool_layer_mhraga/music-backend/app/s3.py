"""S3 as the store of record for the music library and rendered tracks. Local files are a cache."""
from __future__ import annotations

from pathlib import Path

from . import config

_client = None


def client():
    global _client
    if _client is None and config.S3_BUCKET:
        import boto3
        _client = boto3.client("s3", region_name=config.S3_REGION)
    return _client


def upload(path: Path, key: str, content_type: str = "audio/mpeg") -> bool:
    c = client()
    if not c:
        return False
    try:
        c.upload_file(str(path), config.S3_BUCKET, key, ExtraArgs={"ContentType": content_type})
        return True
    except Exception as e:  # e.g. the server role lacks s3:PutObject: keep the song locally, don't fail the job
        print(f"[s3] upload of {key} failed ({str(e)[:120]}); kept on local disk only")
        return False


def fetch(key: str, dest: Path) -> bool:
    """Download key to dest unless already cached. False if S3 is off or the key is missing."""
    if dest.is_file() and dest.stat().st_size:
        return True
    c = client()
    if not c:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        c.download_file(config.S3_BUCKET, key, str(dest))
        return True
    except Exception:
        return False
