"""Phase registry and histogram buckets for inline agent latency."""

from __future__ import annotations

from math import inf
from typing import Dict, Iterable, List

EXECUTION_PATH_INLINE_AGENTS = "inline_agents"

PHASE_TOTAL = "total"
PHASE_BROKER_QUEUE_WAIT = "broker_queue_wait"

PHASES_INLINE_AGENTS: List[str] = [
    "orchestration",
    "pre_generation",
    "generation_setup",
    "agent_execution",
    "post_generation",
]

BOUNDARY_PHASES: List[str] = [
    PHASE_BROKER_QUEUE_WAIT,
]

# Upper bounds in ms (Prometheus-style cumulative histogram)
BUCKET_UPPER_BOUNDS_MS: List[float] = [
    500,
    1000,
    2500,
    5000,
    10000,
    15000,
    20000,
    30000,
    inf,
]


def bucket_key(upper_bound: float) -> str:
    if upper_bound == inf:
        return "inf"
    return str(int(upper_bound))


def cumulative_bucket_key_for_threshold(upper_ms: int) -> str:
    """Return the smallest cumulative histogram bucket key with le >= upper_ms."""
    for le in BUCKET_UPPER_BOUNDS_MS:
        if upper_ms <= le:
            return bucket_key(le)
    return bucket_key(inf)


def empty_buckets() -> Dict[str, int]:
    return {bucket_key(le): 0 for le in BUCKET_UPPER_BOUNDS_MS}


def increment_buckets(buckets: Dict[str, int], duration_ms: int) -> Dict[str, int]:
    """Increment cumulative histogram buckets for one observation."""
    merged = dict(buckets or empty_buckets())
    for le in BUCKET_UPPER_BOUNDS_MS:
        key = bucket_key(le)
        if duration_ms <= le:
            merged[key] = merged.get(key, 0) + 1
    return merged


def phases_for_execution_path(execution_path: str) -> Iterable[str]:
    if execution_path == EXECUTION_PATH_INLINE_AGENTS:
        return list(PHASES_INLINE_AGENTS)
    return []


def rollup_phases_for_turn(
    execution_path: str,
    *,
    total_ms: int,
    phase_ms: Dict[str, int],
    boundaries_ms: Dict[str, int],
) -> Dict[str, int]:
    """Map phase name -> duration_ms for hourly rollup rows."""
    rows: Dict[str, int] = {PHASE_TOTAL: total_ms}
    for phase in phases_for_execution_path(execution_path):
        if phase in phase_ms:
            rows[phase] = int(phase_ms[phase])
    broker_ms = boundaries_ms.get("broker_queue_wait")
    if broker_ms is not None:
        rows[PHASE_BROKER_QUEUE_WAIT] = int(broker_ms)
    return rows
