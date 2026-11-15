"""Accounts: email + password (PBKDF2), session tokens as HS256 JWTs."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException

from . import config

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_fails: dict[str, list[float]] = {}


def _secret() -> str:
    if config.JWT_SECRET:
        return config.JWT_SECRET
    f = config.DATA_DIR / "jwt.secret"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    return salt.hex() + ":" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000).hex()


def verify_password(password: str, stored: str) -> bool:
    salt, _, digest = stored.partition(":")
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)).partition(":")[2], digest)


def valid_email(email: str) -> bool:
    return bool(_EMAIL.match(email)) and len(email) <= 254


def make_token(email: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=config.TOKEN_DAYS)
    return jwt.encode({"sub": email, "exp": exp}, _secret(), algorithm="HS256")


def read_token(token: str) -> str | None:
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        return None


def throttle(email: str) -> None:
    """At most 5 failed sign-ins per email per minute."""
    now = time.time()
    recent = [t for t in _fails.get(email, []) if now - t < 60]
    _fails[email] = recent
    if len(recent) >= 5:
        raise HTTPException(429, "Too many attempts. Wait a minute and try again.")


def record_failure(email: str) -> None:
    _fails.setdefault(email, []).append(time.time())


def akanade_login(email: str, password: str) -> dict | None:
    """Validate email+password against Kalkee's real login, then read the person's name and role.
    Returns {name, role, token} on success (the token is the user's own Kalkee token), else None."""
    from . import config
    if not config.AKANADE_AUTH_URL:
        return None
    try:
        import httpx
        r = httpx.post(f"{config.AKANADE_AUTH_URL}/api/auth/login", json={"email": email, "password": password}, timeout=8)
        tok = r.json().get("access_token") if r.status_code == 200 else None
        if not tok:
            return None
        me = httpx.get(f"{config.AKANADE_AUTH_URL}/api/users/me", headers={"Authorization": f"Bearer {tok}"}, timeout=8).json()
        return {"name": me.get("name") or email.split("@")[0], "role": str(me.get("role") or ""), "token": tok}
    except Exception:
        return None
