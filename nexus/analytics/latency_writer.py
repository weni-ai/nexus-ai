"""Persist inline agent turn latency to Postgres (Plan B)."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

import sentry_sdk
from django.conf import settings
from django.db import IntegrityError, transaction

from nexus.analytics.latency_phases import (
    EXECUTION_PATH_INLINE_AGENTS,
    increment_buckets,
    rollup_phases_for_turn,
)
from nexus.analytics.models import InlineAgentLatencyHourly, InlineAgentTurnOutlier

logger = logging.getLogger(__name__)

SAMPLE_REASON_THRESHOLD = "threshold"
SAMPLE_REASON_FAILED = "failed"
SAMPLE_REASON_BLOCKED = "blocked"
SAMPLE_REASON_BROKER = "broker_threshold"
SAMPLE_REASON_ELEVATED = "elevated_sample"
SAMPLE_REASON_RANDOM = "random_sample"


@dataclass
class TurnCorrelation:
    contact_urn: str = ""
    message_conversation_log_uuid: str = ""
    channel_type: str = ""
    execution_path: str = EXECUTION_PATH_INLINE_AGENTS


def _latency_settings() -> Dict[str, Any]:
    return {
        "enabled": getattr(settings, "INLINE_AGENT_LATENCY_ENABLED", True),
        "outlier_ms": int(getattr(settings, "INLINE_AGENT_LATENCY_OUTLIER_MS", 30000)),
        "broker_outlier_ms": int(getattr(settings, "INLINE_AGENT_LATENCY_BROKER_OUTLIER_MS", 2000)),
        "elevated_ms": int(getattr(settings, "INLINE_AGENT_LATENCY_ELEVATED_MS", 15000)),
        "sample_rate": float(getattr(settings, "INLINE_AGENT_LATENCY_SAMPLE_RATE", 0.001)),
        "elevated_sample_rate": float(getattr(settings, "INLINE_AGENT_LATENCY_ELEVATED_SAMPLE_RATE", 0.01)),
    }


def _truncate_hour(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0)


def _ms_from_seconds(value: Optional[float]) -> Optional[int]:
    if value is None:
        return None
    return max(0, int(round(value * 1000)))


def decide_outlier_sample(
    *,
    status: str,
    total_ms: int,
    broker_wait_ms: Optional[int],
    cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Optional[str]]:
    cfg = cfg or _latency_settings()
    if status == "failed":
        return True, SAMPLE_REASON_FAILED
    if status == "blocked":
        return True, SAMPLE_REASON_BLOCKED
    if total_ms >= cfg["outlier_ms"]:
        return True, SAMPLE_REASON_THRESHOLD
    if broker_wait_ms is not None and broker_wait_ms >= cfg["broker_outlier_ms"]:
        return True, SAMPLE_REASON_BROKER
    elevated_ms = cfg["elevated_ms"]
    outlier_ms = cfg["outlier_ms"]
    elevated_rate = cfg["elevated_sample_rate"]
    if elevated_rate > 0 and elevated_ms <= total_ms < outlier_ms:
        if random.random() < elevated_rate:
            return True, SAMPLE_REASON_ELEVATED
    sample_rate = cfg["sample_rate"]
    if sample_rate > 0 and random.random() < sample_rate:
        return True, SAMPLE_REASON_RANDOM
    return False, None


def _upsert_rollup_row(
    *,
    project_uuid: str,
    hour_ts: datetime,
    execution_path: str,
    phase: str,
    duration_ms: int,
    status: str,
) -> None:
    filters = {
        "project_uuid": project_uuid,
        "hour_ts": hour_ts,
        "execution_path": execution_path,
        "phase": phase,
    }
    create_defaults = {
        "turn_count": 1,
        "sum_ms": duration_ms,
        "max_ms": duration_ms,
        "buckets": increment_buckets({}, duration_ms),
        "error_count": 1 if status == "failed" else 0,
        "blocked_count": 1 if status == "blocked" else 0,
    }

    try:
        row = InlineAgentLatencyHourly.objects.select_for_update().get(**filters)
    except InlineAgentLatencyHourly.DoesNotExist:
        try:
            with transaction.atomic():
                InlineAgentLatencyHourly.objects.create(**filters, **create_defaults)
            return
        except IntegrityError:
            row = InlineAgentLatencyHourly.objects.select_for_update().get(**filters)

    row.turn_count += 1
    row.sum_ms += duration_ms
    row.max_ms = max(row.max_ms, duration_ms)
    row.buckets = increment_buckets(row.buckets, duration_ms)
    if status == "failed":
        row.error_count += 1
    if status == "blocked":
        row.blocked_count += 1
    row.save(
        update_fields=[
            "turn_count",
            "sum_ms",
            "max_ms",
            "buckets",
            "error_count",
            "blocked_count",
        ]
    )


def record_turn_latency(
    *,
    project_uuid: str,
    status: str,
    total_seconds: float,
    phase_seconds: Dict[str, float],
    correlation: TurnCorrelation,
    task_id: str,
    turn_id: str,
    enqueued_at: Optional[float] = None,
    started_at: Optional[float] = None,
    router_received_at: Optional[float] = None,
    context: Optional[Dict[str, Any]] = None,
    finished_at: Optional[datetime] = None,
) -> None:
    cfg = _latency_settings()
    if not cfg["enabled"]:
        return

    finished = finished_at or datetime.now(timezone.utc)
    hour_ts = _truncate_hour(finished)
    total_ms = _ms_from_seconds(total_seconds) or 0
    phase_ms = {k: _ms_from_seconds(v) or 0 for k, v in phase_seconds.items()}

    boundaries_ms: Dict[str, int] = {}
    if enqueued_at is not None and started_at is not None:
        boundaries_ms["broker_queue_wait"] = max(0, _ms_from_seconds(started_at - enqueued_at) or 0)
    if router_received_at is not None and enqueued_at is not None:
        boundaries_ms["router_to_enqueue"] = max(0, _ms_from_seconds(enqueued_at - router_received_at) or 0)

    broker_wait_ms = boundaries_ms.get("broker_queue_wait")

    try:
        with transaction.atomic():
            phase_durations = rollup_phases_for_turn(
                correlation.execution_path,
                total_ms=total_ms,
                phase_ms=phase_ms,
                boundaries_ms=boundaries_ms,
            )
            for phase, duration_ms in phase_durations.items():
                _upsert_rollup_row(
                    project_uuid=project_uuid,
                    hour_ts=hour_ts,
                    execution_path=correlation.execution_path,
                    phase=phase,
                    duration_ms=duration_ms,
                    status=status,
                )

            store, sample_reason = decide_outlier_sample(
                status=status,
                total_ms=total_ms,
                broker_wait_ms=broker_wait_ms,
                cfg=cfg,
            )
            if store and sample_reason:
                router_dt = None
                if router_received_at is not None:
                    router_dt = datetime.fromtimestamp(router_received_at, tz=timezone.utc)
                log_uuid = None
                if correlation.message_conversation_log_uuid:
                    try:
                        log_uuid = UUID(str(correlation.message_conversation_log_uuid))
                    except (ValueError, TypeError, AttributeError):
                        log_uuid = None
                InlineAgentTurnOutlier.objects.create(
                    project_uuid=project_uuid,
                    execution_path=correlation.execution_path,
                    turn_finished_at=finished,
                    contact_urn=correlation.contact_urn[:512],
                    turn_id=turn_id[:255],
                    message_conversation_log_uuid=log_uuid,
                    channel_type=(correlation.channel_type or "")[:32],
                    celery_task_id=(task_id or "")[:255],
                    status=status,
                    total_ms=total_ms,
                    boundaries_ms=boundaries_ms,
                    phase_ms=phase_ms,
                    context=context or {},
                    router_received_at=router_dt,
                    sample_reason=sample_reason,
                )
    except Exception as exc:
        logger.exception(
            "Failed to persist inline agent latency",
            extra={"project_uuid": project_uuid, "turn_id": turn_id, "task_id": task_id},
        )
        sentry_sdk.capture_exception(exc)
