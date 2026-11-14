from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _route_payload(**context_overrides):
    return {
        "candidates": [
            {"id": "luna", "cost_per_1k_tokens": 0.02, "capability_tier": 0.9},
            {"id": "groq", "cost_per_1k_tokens": 0.001, "capability_tier": 0.7},
            {"id": "algo-akanade-slm", "cost_per_1k_tokens": 0.0, "capability_tier": 0.5},
        ],
        "context": {"tier": "realtime", "est_tokens": 500, "task_min_capability": 0.0,
                    **context_overrides},
    }


def test_route_is_always_deterministic():
    # No exploration policy of any kind — /route's outcome is a pure
    # function of its own inputs every time, nothing to toggle.
    resp = client.post("/route", json=_route_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["strategy_used"] == "deterministic"
    assert set(body["ordered_ids"]) == {"luna", "groq", "algo-akanade-slm"}


def test_routing_option_defaults_to_openrouter_when_omitted():
    resp = client.post("/route", json=_route_payload())
    assert resp.json()["routing_option"] == "openrouter"


def test_routing_option_is_echoed_back_when_the_caller_sets_one():
    payload = _route_payload()
    payload["routing_option"] = "both"
    resp = client.post("/route", json=payload)
    assert resp.json()["routing_option"] == "both"


def test_slm_routing_option_is_accepted_but_does_not_change_the_order_yet():
    # Honest about status — see ARCHITECTURE.md §6: the SLM Engine isn't
    # wired into this decision yet, so "slm" is accepted and echoed back,
    # but ordered_ids is still today's real deterministic behavior.
    payload = _route_payload()
    payload["routing_option"] = "slm"
    resp = client.post("/route", json=payload)
    body = resp.json()
    assert body["routing_option"] == "slm"
    assert body["strategy_used"] == "deterministic"
    assert set(body["ordered_ids"]) == {"luna", "groq", "algo-akanade-slm"}


def test_route_orders_cheapest_expected_cost_first():
    resp = client.post("/route", json=_route_payload())
    body = resp.json()
    # groq (cheap, still eligible) should rank ahead of luna (expensive)
    # among candidates meeting task_min_capability — see deterministic.py.
    assert body["ordered_ids"].index("groq") < body["ordered_ids"].index("luna")


def test_route_pushes_ineligible_candidates_to_the_back_not_out():
    resp = client.post("/route", json=_route_payload(task_min_capability=0.6))
    body = resp.json()
    # algo-akanade-slm (capability 0.5) is below the bar but still present,
    # just last — a caller's own fallback walk keeps every real option.
    assert body["ordered_ids"][-1] == "algo-akanade-slm"
    assert set(body["ordered_ids"]) == {"luna", "groq", "algo-akanade-slm"}


def test_outcome_accepts_and_persists():
    resp = client.post("/outcome", json={
        "candidate_id": "groq", "ok": True, "latency_ms": 250.0, "cost_usd": 0.001,
        "strategy_used": "deterministic", "tier": "realtime",
    })
    assert resp.status_code == 204


def test_admin_routing_outcomes_returns_logged_rows():
    client.post("/outcome", json={
        "candidate_id": "groq", "ok": True, "latency_ms": 123.0, "cost_usd": 0.002,
        "strategy_used": "deterministic", "tier": "realtime",
    })
    resp = client.get("/admin/routing-outcomes", params={"limit": 5000})
    assert resp.status_code == 200
    rows = resp.json()
    assert any(r["chosen"] == "groq" for r in rows)


def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "pecova"}
