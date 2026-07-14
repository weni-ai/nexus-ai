"""Turn-level latency recording for start_inline_agents (Phase 0)."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Optional
from uuid import UUID

import sentry_sdk

from router.tasks.inline_agent_metrics import (
    INLINE_AGENT_BROKER_QUEUE_WAIT_SECONDS,
    INLINE_AGENT_ERRORS_TOTAL,
    INLINE_AGENT_PHASE_DURATION_SECONDS,
    INLINE_AGENT_ROUTER_TO_ENQUEUE_SECONDS,
    INLINE_AGENT_TURN_DURATION_SECONDS,
    INLINE_AGENT_TURN_MISSING_PROJECT_UUID_TOTAL,
    INLINE_AGENT_WORKER_SCHEDULING_DELAY_SECONDS,
)
from nexus.inline_agent_latency_headers import (
    HEADER_ENQUEUED_AT,
    HEADER_PROJECT_UUID,
    HEADER_RECEIVED_AT,
    HEADER_STARTED_AT,
)

logger = logging.getLogger(__name__)

PHASE_ORCHESTRATION = "orchestration"
PHASE_PRE_GENERATION = "pre_generation"
PHASE_GENERATION_SETUP = "generation_setup"
PHASE_AGENT_EXECUTION = "agent_execution"
PHASE_POST_GENERATION = "post_generation"

TURN_STATUS_SUCCESS = "success"
TURN_STATUS_BLOCKED = "blocked"
TURN_STATUS_FAILED = "failed"


def parse_valid_project_uuid(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return str(UUID(text))
    except (ValueError, TypeError, AttributeError):
        return None


def _header_float(headers: Optional[Dict], key: str) -> Optional[float]:
    if not headers:
        return None
    raw = headers.get(key)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def report_missing_project_uuid(reason: str, task_id: Optional[str] = None) -> None:
    INLINE_AGENT_TURN_MISSING_PROJECT_UUID_TOTAL.inc()
    sentry_sdk.set_tag("inline_agent_latency", "missing_project_uuid")
    if task_id:
        sentry_sdk.set_tag("task_id", task_id)
    sentry_sdk.set_context("inline_agent_latency", {"reason": reason})
    sentry_sdk.capture_message(
        f"[InlineAgentLatency] Missing or invalid project_uuid: {reason}",
        level="warning",
    )


@dataclass
class TurnLatencyRecorder:
    """Records phase timings and observes Prometheus metrics once in finish()."""

    project_uuid: str
    turn_id: str
    task_id: str
    metrics_enabled: bool = True
    last_completed_phase: str = ""
    _phase_durations: Dict[str, float] = field(default_factory=dict)
    _turn_start: float = field(default_factory=time.perf_counter)
    _enqueued_at: Optional[float] = None
    _received_at: Optional[float] = None
    _started_at: Optional[float] = None
    _router_received_at: Optional[float] = None
    _finished: bool = False

    def __post_init__(self) -> None:
        if not self.metrics_enabled:
            return
        validated = parse_valid_project_uuid(self.project_uuid)
        if validated is None:
            self.metrics_enabled = False
            report_missing_project_uuid("invalid project_uuid", self.task_id)
        else:
            self.project_uuid = validated

    @classmethod
    def from_message_and_request(
        cls,
        message: Dict,
        request: Any,
        *,
        turn_id: str,
    ) -> TurnLatencyRecorder:
        task_id = getattr(request, "id", None) or ""
        headers = getattr(request, "headers", None) or {}

        project_uuid = parse_valid_project_uuid(message.get("project_uuid")) or parse_valid_project_uuid(
            headers.get(HEADER_PROJECT_UUID)
        )
        metrics_enabled = project_uuid is not None
        if not metrics_enabled:
            report_missing_project_uuid("missing in message and headers", task_id)

        router_received_at = message.get("router_received_at")
        router_ts = None
        if router_received_at is not None:
            try:
                router_ts = float(router_received_at)
            except (TypeError, ValueError):
                pass

        enqueued_at = _header_float(headers, HEADER_ENQUEUED_AT)
        if enqueued_at is None:
            raw_enqueued = message.get("inline_agent_enqueued_at")
            if raw_enqueued is not None:
                try:
                    enqueued_at = float(raw_enqueued)
                except (TypeError, ValueError):
                    enqueued_at = None

        return cls(
            project_uuid=project_uuid or "",
            turn_id=turn_id,
            task_id=task_id,
            metrics_enabled=metrics_enabled,
            _enqueued_at=enqueued_at,
            _received_at=_header_float(headers, HEADER_RECEIVED_AT),
            _started_at=_header_float(headers, HEADER_STARTED_AT),
            _router_received_at=router_ts,
        )

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self._phase_durations[name] = time.perf_counter() - start
            self.last_completed_phase = name

    def finish(self, status: str, *, record_error: bool = False) -> None:
        if self._finished:
            return
        self._finished = True

        if not self.metrics_enabled:
            return

        project_uuid = self.project_uuid
        total_seconds = time.perf_counter() - self._turn_start

        if self._enqueued_at is not None and self._started_at is not None:
            broker_wait = max(0.0, self._started_at - self._enqueued_at)
            INLINE_AGENT_BROKER_QUEUE_WAIT_SECONDS.labels(project_uuid=project_uuid).observe(broker_wait)

        if self._received_at is not None and self._started_at is not None:
            scheduling = max(0.0, self._started_at - self._received_at)
            INLINE_AGENT_WORKER_SCHEDULING_DELAY_SECONDS.labels(project_uuid=project_uuid).observe(scheduling)

        if self._router_received_at is not None and self._enqueued_at is not None:
            router_to_enqueue = max(0.0, self._enqueued_at - self._router_received_at)
            INLINE_AGENT_ROUTER_TO_ENQUEUE_SECONDS.labels(project_uuid=project_uuid).observe(router_to_enqueue)

        for phase_name, duration in self._phase_durations.items():
            INLINE_AGENT_PHASE_DURATION_SECONDS.labels(phase=phase_name, project_uuid=project_uuid).observe(duration)

        INLINE_AGENT_TURN_DURATION_SECONDS.labels(status=status, project_uuid=project_uuid).observe(total_seconds)

        if record_error and self.last_completed_phase:
            INLINE_AGENT_ERRORS_TOTAL.labels(phase=self.last_completed_phase, project_uuid=project_uuid).inc()

        logger.debug(
            "Inline agent turn latency",
            extra={
                "project_uuid": project_uuid,
                "turn_id": self.turn_id,
                "task_id": self.task_id,
                "status": status,
                "total_seconds": round(total_seconds, 4),
                "phases": {k: round(v, 4) for k, v in self._phase_durations.items()},
                "last_completed_phase": self.last_completed_phase,
            },
        )

    def apply_sentry_tags(self) -> None:
        if not self.metrics_enabled:
            return
        sentry_sdk.set_tag("project_uuid", self.project_uuid)
        sentry_sdk.set_tag("turn_id", self.turn_id)
        sentry_sdk.set_tag("task_id", self.task_id)
        if self.last_completed_phase:
            sentry_sdk.set_tag("last_completed_phase", self.last_completed_phase)


def record_cache_access(project_uuid: str, cache_type: str, hit: bool) -> None:
    validated = parse_valid_project_uuid(project_uuid)
    if validated is None:
        return
    from router.tasks.inline_agent_metrics import INLINE_AGENT_CACHE_ACCESS_TOTAL

    INLINE_AGENT_CACHE_ACCESS_TOTAL.labels(
        cache_type=cache_type,
        hit="true" if hit else "false",
        project_uuid=validated,
    ).inc()


def cache_type_from_key(cache_key: str) -> Optional[str]:
    if not cache_key.startswith("project:"):
        return None
    parts = cache_key.split(":")
    if len(parts) >= 3:
        return parts[2]
    return None


def project_uuid_from_cache_key(cache_key: str) -> Optional[str]:
    if not cache_key.startswith("project:"):
        return None
    parts = cache_key.split(":")
    if len(parts) >= 2:
        return parse_valid_project_uuid(parts[1])
    return None
