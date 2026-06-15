"""Redis-backed job state for Flows vs DB cohort reconcile (JSON polling)."""

from __future__ import annotations

from typing import Any, Literal

from django.conf import settings
from django.core.cache import cache

JobDelivery = Literal["email", "json"]
JobStatus = Literal["queued", "running", "completed", "failed"]

_CACHE_PREFIX = "flows_db_cohort:job:"

DELIVERY_EMAIL: JobDelivery = "email"
DELIVERY_JSON: JobDelivery = "json"

STATUS_QUEUED: JobStatus = "queued"
STATUS_RUNNING: JobStatus = "running"
STATUS_COMPLETED: JobStatus = "completed"
STATUS_FAILED: JobStatus = "failed"


def _job_key(job_id: str) -> str:
    return f"{_CACHE_PREFIX}{job_id}"


def _default_ttl() -> int:
    return int(getattr(settings, "FLOWS_DB_COHORT_JOB_RESULT_TTL", 86_400))


def _write_job(job_id: str, payload: dict[str, Any], *, timeout: int | None = None) -> None:
    cache.set(_job_key(job_id), payload, timeout=timeout or _default_ttl())


def create_job(
    job_id: str,
    *,
    project_id: str,
    delivery: JobDelivery,
    requested_range: dict[str, str],
    recipient_email: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "job_id": job_id,
        "project_id": project_id,
        "delivery": delivery,
        "status": STATUS_QUEUED,
        "requested_range": requested_range,
        "recipient_email": recipient_email,
        "report": None,
        "error": None,
    }
    _write_job(job_id, payload)
    return payload


def get_job(job_id: str) -> dict[str, Any] | None:
    data = cache.get(_job_key(job_id))
    if not isinstance(data, dict):
        return None
    return data


def set_job_running(job_id: str) -> dict[str, Any] | None:
    payload = get_job(job_id)
    if payload is None:
        return None
    payload["status"] = STATUS_RUNNING
    _write_job(job_id, payload)
    return payload


def set_job_completed(job_id: str, report: dict[str, Any]) -> dict[str, Any] | None:
    payload = get_job(job_id)
    if payload is None:
        return None
    payload["status"] = STATUS_COMPLETED
    payload["report"] = report
    payload["error"] = None
    _write_job(job_id, payload)
    return payload


def set_job_failed(
    job_id: str,
    error_message: str,
    *,
    report: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    payload = get_job(job_id)
    if payload is None:
        return None
    payload["status"] = STATUS_FAILED
    payload["error"] = error_message
    if report is not None:
        payload["report"] = report
    _write_job(job_id, payload)
    return payload


def build_job_poll_response(job: dict[str, Any]) -> dict[str, Any]:
    """Public fields returned by the poll endpoint."""
    response: dict[str, Any] = {
        "job_id": job.get("job_id"),
        "project_id": job.get("project_id"),
        "delivery": job.get("delivery"),
        "status": job.get("status"),
        "requested_range": job.get("requested_range"),
    }
    status = job.get("status")
    if status == STATUS_COMPLETED:
        response["report"] = job.get("report")
    elif status == STATUS_FAILED:
        response["error"] = job.get("error")
        if job.get("report") is not None:
            response["report"] = job.get("report")
    return response
