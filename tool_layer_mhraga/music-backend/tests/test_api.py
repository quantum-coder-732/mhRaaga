import os
import tempfile
import time

os.environ["MUSIC_DATA_DIR"] = tempfile.mkdtemp()
os.environ["MUSIC_SEED_SAMPLES"] = "0"
os.environ["MUSIC_ALLOW_GUEST"] = "1"
os.environ.pop("DYNAMO_ENDPOINT", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

U = {"X-User-Id": "alice"}


def _generate(c, prompt, **kw):
    job = c.post("/api/music/generate", json={"prompt": prompt, "duration_seconds": 20, **kw}, headers=U).json()["job_id"]
    for _ in range(100):
        r = c.get(f"/api/music/jobs/{job}", headers=U).json()
        if r["status"] in ("COMPLETED", "FAILED"):
            return r
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_generate_discover_like_and_stream():
    with TestClient(app) as c:
        r = _generate(c, "a calm Yaman bhajan to Krishna", title="Test Bhajan")
        assert r["status"] == "COMPLETED", r
        assert r["track"]["raga"] == "yaman" and r["track"]["title"] == "Test Bhajan"
        tid = r["track"]["id"]
        assert c.get("/api/music/tracks", params={"q": "yaman"}, headers=U).json()["tracks"][0]["id"] == tid
        assert c.post(f"/api/music/tracks/{tid}/like", headers=U).json()["liked"] is True
        assert c.post(f"/api/music/tracks/{tid}/like", headers=U).json()["liked"] is False
        assert c.post(f"/api/music/tracks/{tid}/play", headers=U).json()["plays"] == 1
        audio = c.get(r["track"]["audio_url"], headers={"Range": "bytes=0-9"})
        assert audio.status_code == 206 and len(audio.content) == 10


def test_private_tracks_hidden_from_others_and_validation():
    with TestClient(app) as c:
        tid = _generate(c, "private lofi beat", public=False)["track"]["id"]
        assert c.get(f"/api/music/tracks/{tid}", headers={"X-User-Id": "bob"}).status_code == 404
        assert c.get(f"/api/music/tracks/{tid}", headers=U).status_code == 200
        assert c.post("/api/music/generate", json={"prompt": "x"}, headers=U).status_code == 422
        assert c.get("/api/music/audio/..%2Fstore.json").status_code == 404


def test_brain_uses_akanade_brief_when_available(monkeypatch):
    import json

    from app import brain, config

    class R:
        def raise_for_status(self): pass
        def json(self):
            return {"selected_agents": ["pecova-music-agent"],
                    "result": {"text": json.dumps({"title": "T", "genre": "raga", "raga": "todi", "language": "hindi",
                                                    "taal": "teental", "tempo_bpm": 70, "mood": "calm",
                                                    "instruments": ["flute"], "lyrics": ""})}}

    monkeypatch.setattr(config, "AKANADE_TOKEN", "tok")
    monkeypatch.setattr(brain.httpx, "post", lambda *a, **k: R())
    b = brain.compose("anything", duration=40)
    assert b["source"] == "akanade" and b["raga"] == "todi" and b["duration_seconds"] == 40
    monkeypatch.setattr(brain.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    assert brain.compose("calm yaman raga")["source"] == "fallback"


def test_signup_login_me_and_protected_routes(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "ALLOW_GUEST", False)
    with TestClient(app) as c:
        assert c.get("/api/music/tracks").status_code == 401
        r = c.post("/api/auth/signup", json={"name": "Asha", "email": "Asha@Example.com", "password": "longenough1"})
        assert r.status_code == 201 and r.json()["user"]["email"] == "asha@example.com"
        assert c.post("/api/auth/signup", json={"name": "A", "email": "asha@example.com", "password": "longenough1"}).status_code == 409
        assert c.post("/api/auth/signup", json={"name": "A", "email": "bad", "password": "longenough1"}).status_code == 422
        assert c.post("/api/auth/signup", json={"name": "A", "email": "x@y.zz", "password": "short"}).status_code == 422
        bad = c.post("/api/auth/login", json={"email": "asha@example.com", "password": "wrong-pass"})
        assert bad.status_code == 401
        tok = c.post("/api/auth/login", json={"email": "asha@example.com", "password": "longenough1"}).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        assert c.get("/api/auth/me", headers=h).json()["name"] == "Asha"
        assert c.get("/api/music/tracks", headers=h).status_code == 200
        assert c.get("/api/music/tracks", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_login_is_throttled(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "ALLOW_GUEST", False)
    with TestClient(app) as c:
        codes = [c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"}).status_code for _ in range(7)]
        assert codes[:5] == [401] * 5 and codes[5] == 429
