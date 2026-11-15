"""Kalkee's core routing endpoints — "given these eligible candidates,
what order should the caller try them in." Deliberately no auth here —
this service is only reachable on the internal Docker network, never
exposed publicly; the caller (Kalkee) does its own auth/role-gating
before it ever gets here.

No exploration/bandit policy of any kind: every decision here is
deterministic and explainable from its own inputs — see
deterministic.py's docstring. The RouteLLM-based difficulty classifier
in generic_architecture.py is a separate, OPT-IN comparison arm exposed
under /generic-architecture (routes_generic.py), never the default path.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter

from . import deterministic
from .db import store
from .models import OutcomeRequest, RouteRequest, RouteResponse

router = APIRouter()


@router.post("/route", response_model=RouteResponse)
def route(payload: RouteRequest) -> RouteResponse:
    # "slm" is accepted and echoed back honestly — it does not change
    # ordered_ids yet, since the SLM Engine isn't wired into this decision
    # yet (see ARCHITECTURE.md §6's status note). Every other value
    # (including "both", and no value at all) gets today's real behavior.
    ordered = deterministic.order(payload.candidates, payload.context)
    routing_option = payload.routing_option or "openrouter"
    return RouteResponse(ordered_ids=ordered, strategy_used="deterministic", routing_option=routing_option)


@router.post("/outcome", status_code=204)
def outcome(payload: OutcomeRequest) -> None:
    """Pure telemetry — logs every outcome so the Routing dashboard has a
    full picture. Never feeds back into /route's own decision (there is
    no adaptive/exploration policy to feed)."""
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tier": payload.tier,
        "chosen": payload.candidate_id,
        "strategyUsed": payload.strategy_used,
        "ok": payload.ok,
        "costUsd": payload.cost_usd,
        "latencyMs": payload.latency_ms,
    }
    store("RoutingOutcomes").put(f"OUTCOME#{uuid.uuid4().hex[:12]}", "META", row)


@router.get("/admin/routing-outcomes")
def list_routing_outcomes(since: str | None = None, until: str | None = None,
                          limit: int = 2000) -> list[dict]:
    """Raw feed for the Routing dashboard. No auth here — same internal-
    network-only trust boundary as every other route in this file; RBAC
    happens on the caller's (Kalkee's) proxy side."""
    rows = store("RoutingOutcomes").scan(pk_prefix="OUTCOME#")
    if since:
        rows = [r for r in rows if r.get("timestamp", "") >= since]
    if until:
        rows = [r for r in rows if r.get("timestamp", "") <= until]
    rows.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return rows[:limit]
