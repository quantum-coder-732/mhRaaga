"""Per-song cost ledger (USD, estimates). Called once per rendered track and stored on the track."""
from __future__ import annotations

from . import config


def song_cost(*, polly_chars: int, llm_in: int, llm_out: int, llm_estimated: bool, render_seconds: float,
              size_bytes: int, duration_seconds: int, llm_cost: float | None = None) -> dict:
    polly = polly_chars / 1e6 * config.PRICE_POLLY_NEURAL_PER_M_CHARS
    llm = llm_in / 1e6 * config.PRICE_LLM_IN_PER_M_TOKENS + llm_out / 1e6 * config.PRICE_LLM_OUT_PER_M_TOKENS
    if llm_cost is not None:
        llm = float(llm_cost)  # OpenRouter's own billed cost when Kalkee passes it through
    compute = render_seconds / 3600 * config.PRICE_EC2_PER_HOUR
    gb = size_bytes / 1e9
    storage_month = gb * config.PRICE_S3_PER_GB_MONTH
    per_play = gb * config.PRICE_CDN_PER_GB  # one full listen streamed through CloudFront
    one_off = polly + llm + compute
    return {
        "polly_chars": polly_chars, "polly_usd": round(polly, 5),
        "llm_tokens_in": llm_in, "llm_tokens_out": llm_out, "llm_estimated": llm_estimated, "llm_usd": round(llm, 5),
        "render_seconds": round(render_seconds, 1), "compute_usd": round(compute, 5),
        "size_bytes": size_bytes, "storage_usd_month": round(storage_month, 6), "delivery_usd_per_play": round(per_play, 6),
        "create_usd": round(one_off, 5),  # what it cost to make (one-off)
        "usd_per_audio_minute": round(one_off / max(duration_seconds / 60, 1e-9), 5),
    }
