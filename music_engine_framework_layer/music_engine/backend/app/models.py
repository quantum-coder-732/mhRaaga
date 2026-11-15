"""Request/response shapes for Kalkee's /route and /outcome — the ONLY
contract a caller (Kalkee, or Outreach-Ai through it) needs to know
about. No session, no auth, no provider credentials cross this
boundary.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

Strategy = str  # "deterministic" | "routellm"


class Candidate(BaseModel):
    id: str  # registry key — "groq", "algo-akanade-slm", etc., matched
              # against the caller's own provider dict, never a display name.
    cost_per_1k_tokens: float = 0.0
    p95_latency_ms: float = 2000.0
    capability_tier: float = 0.5  # 0..1


class RouteContext(BaseModel):
    tier: str = "realtime"  # "realtime" | "delay_ok" | "bulk"
    est_tokens: int = 500
    task_min_capability: float = 0.0
    # The actual latest user message text — optional, and the one field
    # here that's more than lightweight metadata. Only populated when the
    # caller wants the RouteLLM difficulty classifier in generic_architecture.py
    # to see the real prompt; unset, /route behaves purely on the metadata above.
    prompt: str | None = None


RoutingOption = str  # "openrouter" | "both" | "slm" — see integrations.py's own Literal for the authoritative definition


class RouteRequest(BaseModel):
    candidates: list[Candidate]
    context: RouteContext
    # THIS is the field a caller sets to choose, per request, which path
    # answers — among whatever its integration key was approved for (that
    # authorization check happens at Kalkee's gateway, before the request
    # ever reaches Kalkee; this service trusts what it's handed). Omitted
    # means "whatever the integration's own approved routing_option was" —
    # only meaningful to set explicitly for an integration approved for
    # "both", to pick one specific path for one specific call.
    routing_option: RoutingOption | None = None


class RouteResponse(BaseModel):
    ordered_ids: list[str]
    strategy_used: Strategy
    # Echoes back whichever routing_option actually governed this
    # decision — the request's own override if it set one, else the
    # caller's integration-level default. "openrouter" today, always;
    # "slm" is accepted and echoed back honestly, but doesn't change
    # ordered_ids yet — see ARCHITECTURE.md §6's own status note.
    routing_option: RoutingOption = "openrouter"


class OutcomeRequest(BaseModel):
    candidate_id: str
    ok: bool
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    strategy_used: Strategy
    tier: str = "realtime"
    context_vector: list[float] = Field(default_factory=list)


class RouterConfigOut(BaseModel):
    strategy: Strategy
    updated_by: str | None = None
    updated_at: str | None = None


class RouterConfigIn(BaseModel):
    strategy: Strategy
    updated_by: str
