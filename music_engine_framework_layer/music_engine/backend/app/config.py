"""Minimal settings for Pecova — deliberately NOT a copy of Akanade's full
app/config.py (dozens of provider API keys this service never touches).
Only what db.py's store() and the routing strategies need.

Shares the same DynamoDB (or DynamoDB-local) instance as Akanade's own
backend via the same DYNAMO_ENDPOINT/DYNAMO_REGION env vars — this is how
RouterConfig/RoutingOutcomes/ModelBenchmarks end up visible to both
services without any new database infrastructure. Pecova is stateless
about Akanade's own session/policy state.
"""
from __future__ import annotations

import os


class Settings:
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local")
    DATA_DIR: str = os.getenv("DATA_DIR", os.path.join(os.getcwd(), "data"))
    DYNAMO_ENDPOINT: str = os.getenv("DYNAMO_ENDPOINT", "")
    DYNAMO_REGION: str = os.getenv("AWS_REGION", "ap-south-1")

    # Fallback default if the RouterConfig DB row doesn't exist yet (a
    # brand-new deployment, before any admin has touched anything).
    DEFAULT_ROUTING_STRATEGY: str = "deterministic"


_settings = Settings()


def settings() -> Settings:
    return _settings
