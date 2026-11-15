"""Kalkee — the backend engine behind Algo Kalkee's integrations (Outreach-Ai
and others). Deliberately tiny at this layer: no session state, no provider
credentials, no chat/tool logic — just "given these eligible candidates, what
order should the caller try them in," plus the opt-in RouteLLM comparison arm.
See ../../ARCHITECTURE.md for the full picture (KALKEE, the two routing
options, and how this service fits between Kalkee and an integration like
Outreach-Ai).
"""
from __future__ import annotations

from fastapi import FastAPI

from .routes import router
from .routes_generic import router as generic_router

app = FastAPI(title="Kalkee", version="1.0")
app.include_router(router)
app.include_router(generic_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "pecova"}
