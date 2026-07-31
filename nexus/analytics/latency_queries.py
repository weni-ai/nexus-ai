"""Read models for inline agent latency analytics."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.db.models import QuerySet, Sum

from nexus.analytics.latency_phases import BUCKET_UPPER_BOUNDS_MS, PHASE_TOTAL, bucket_key
from nexus.analytics.models import InlineAgentLatencyHourly, InlineAgentTurnOutlier

MAX_QUERY_DAYS = 90


def validate_project_uuid(project_uuid: str) -> Optional[str]:
    from router.tasks.latency_context import parse_valid_project_uuid

    return parse_valid_project_uuid(project_uuid)


def validate_date_range(start_date: date, end_date: date) -> Optional[str]:
    if start_date > end_date:
        return "start_date must be before or equal to end_date"
    if (end_date - start_date).days > MAX_QUERY_DAYS:
        return f"Date range cannot exceed {MAX_QUERY_DAYS} days"
    return None


def _datetime_range(start_date: date, end_date: date) -> Tuple[datetime, datetime]:
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return start_dt, end_dt


def _hourly_queryset(
    project_uuid: str,
    start_date: date,
    end_date: date,
    *,
    execution_path: str = "inline_agents",
    phase: str = PHASE_TOTAL,
) -> QuerySet[InlineAgentLatencyHourly]:
    start_dt, end_dt = _datetime_range(start_date, end_date)
    return InlineAgentLatencyHourly.objects.filter(
        project_uuid=project_uuid,
        hour_ts__gte=start_dt,
        hour_ts__lt=end_dt,
        execution_path=execution_path,
        phase=phase,
    ).order_by("hour_ts")


def merge_buckets(rows: QuerySet[InlineAgentLatencyHourly]) -> Dict[str, int]:
    merged: Dict[str, int] = {}
    for row in rows:
        for key, count in (row.buckets or {}).items():
            merged[key] = merged.get(key, 0) + int(count)
    return merged


def estimate_p95_ms(buckets: Dict[str, int], total_count: int) -> Optional[int]:
    if total_count <= 0 or not buckets:
        return None
    target = int(total_count * 0.95)
    if target <= 0:
        target = 1
    cumulative = 0
    for le in BUCKET_UPPER_BOUNDS_MS:
        key = bucket_key(le)
        cumulative += int(buckets.get(key, 0))
        if cumulative >= target:
            if le == float("inf"):
                return None
            return int(le)
    return None


def pct_at_or_below_bucket(buckets: Dict[str, int], total_count: int, upper_ms: int) -> Optional[float]:
    if total_count <= 0:
        return None
    key = bucket_key(float(upper_ms))
    count = int(buckets.get(key, 0))
    return round(100.0 * count / total_count, 2)


def build_summary(
    project_uuid: str,
    start_date: date,
    end_date: date,
    *,
    execution_path: str = "inline_agents",
) -> Dict[str, Any]:
    rows = _hourly_queryset(project_uuid, start_date, end_date, execution_path=execution_path)
    agg = rows.aggregate(
        turn_count=Sum("turn_count"),
        sum_ms=Sum("sum_ms"),
    )
    turn_count = int(agg["turn_count"] or 0)
    sum_ms = int(agg["sum_ms"] or 0)
    max_ms = max((row.max_ms for row in rows), default=0)
    buckets = merge_buckets(rows)

    target_high = int(getattr(settings, "INLINE_AGENT_LATENCY_TARGET_MS_HIGH", 20000))
    outlier_ms = int(getattr(settings, "INLINE_AGENT_LATENCY_OUTLIER_MS", 30000))

    return {
        "project_uuid": project_uuid,
        "execution_path": execution_path,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "turn_count": turn_count,
        "avg_ms": round(sum_ms / turn_count, 2) if turn_count else None,
        "max_ms": max_ms,
        "p95_estimate_ms": estimate_p95_ms(buckets, turn_count),
        "pct_under_target_high_ms": pct_at_or_below_bucket(buckets, turn_count, target_high),
        "pct_over_max_tolerable_ms": _pct_over_max_tolerable(buckets, turn_count, outlier_ms),
    }


def _pct_over_max_tolerable(buckets: Dict[str, int], total_count: int, outlier_ms: int) -> Optional[float]:
    if total_count <= 0:
        return None
    # cumulative bucket at outlier_ms is count <= outlier_ms
    at_or_below = int(buckets.get(bucket_key(float(outlier_ms)), 0))
    over = total_count - at_or_below
    return round(100.0 * over / total_count, 2)


def build_timeseries(
    project_uuid: str,
    start_date: date,
    end_date: date,
    *,
    execution_path: str = "inline_agents",
    phase: str = PHASE_TOTAL,
) -> List[Dict[str, Any]]:
    rows = _hourly_queryset(
        project_uuid, start_date, end_date, execution_path=execution_path, phase=phase
    )
    series: List[Dict[str, Any]] = []
    for row in rows:
        turn_count = row.turn_count
        series.append(
            {
                "hour_ts": row.hour_ts.isoformat().replace("+00:00", "Z"),
                "phase": row.phase,
                "turn_count": turn_count,
                "avg_ms": round(row.sum_ms / turn_count, 2) if turn_count else None,
                "max_ms": row.max_ms,
                "p95_estimate_ms": estimate_p95_ms(row.buckets or {}, turn_count),
            }
        )
    return series


def list_outliers(
    project_uuid: str,
    start_date: date,
    end_date: date,
    *,
    execution_path: str = "inline_agents",
    limit: int = 50,
) -> List[InlineAgentTurnOutlier]:
    start_dt, end_dt = _datetime_range(start_date, end_date)
    limit = min(max(limit, 1), 100)
    return list(
        InlineAgentTurnOutlier.objects.filter(
            project_uuid=project_uuid,
            execution_path=execution_path,
            turn_finished_at__gte=start_dt,
            turn_finished_at__lt=end_dt,
        ).order_by("-total_ms", "-turn_finished_at")[:limit]
    )
