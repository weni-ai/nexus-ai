"""Short-lived storage for per-job Flows API tokens (not queued in Celery args)."""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

_CACHE_PREFIX = "flows_db_cohort:token:"


def _default_ttl() -> int:
    hard = int(getattr(settings, "FLOWS_DB_COHORT_EMAIL_CELERY_TIME_LIMIT", 3600))
    return hard + 300


def store_flows_api_token(job_id: str, token: str, *, timeout: int | None = None) -> None:
    cache.set(f"{_CACHE_PREFIX}{job_id}", token, timeout=timeout or _default_ttl())


def pop_flows_api_token(job_id: str) -> str | None:
    key = f"{_CACHE_PREFIX}{job_id}"
    token = cache.get(key)
    if token is not None:
        cache.delete(key)
    return token


def attach_flows_api_token(cfg: dict, job_id: str) -> dict:
    """Return a copy of ``cfg`` with ``flows_api_token`` loaded from cache (one-time)."""
    token = pop_flows_api_token(job_id)
    if not token:
        raise ValueError("Flows API token expired or missing for this job")
    merged = dict(cfg)
    merged["flows_api_token"] = token
    return merged
