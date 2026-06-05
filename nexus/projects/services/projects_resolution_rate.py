"""Orchestrate projects resolution-rate from nexus-conversations and local project metadata."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import pendulum
from django.db.models import Count, Q

from nexus.inline_agents.models import Agent
from nexus.projects.models import Project

logger = logging.getLogger(__name__)

CONVERSATIONS_METRICS_EARLIEST_DATE = date(2026, 3, 28)
MANAGER_FALLBACK = "2.5"

OPTIONAL_INCLUDE_BLOCKS = frozenset(
    {
        "conversations",
        "csat",
        "nps",
        "manager",
        "agents",
        "components",
    }
)

CONVERSATION_METRIC_FIELDS = (
    "conversation_count",
    "resolved_count",
    "unresolved_count",
    "human_support_count",
)
CSAT_FIELDS = ("csat", "csat_responses_count")
NPS_FIELDS = ("nps", "nps_responses_count")
AGENT_FIELDS = ("agents_count", "official_agents_count")


@dataclass(frozen=True)
class ResolutionRateQuery:
    project_uuids: list[UUID] | None
    start_date: pendulum.Date | None
    end_date: pendulum.Date | None
    page: int
    page_size: int
    include_blocks: set[str] | None


def parse_calendar_date(value: str, field_name: str) -> pendulum.Date:
    try:
        parsed = pendulum.parse(str(value).strip(), exact=True)
    except Exception as e:
        raise ValueError(f"Invalid {field_name} format. Use YYYY-MM-DD") from e
    if isinstance(parsed, pendulum.Date):
        return parsed
    return parsed.date()


def parse_project_uuids(raw_values: list[str]) -> list[UUID]:
    if not raw_values:
        return []
    uuids: list[UUID] = []
    seen: set[UUID] = set()
    for raw in raw_values:
        for part in str(raw).split(","):
            token = part.strip()
            if not token:
                continue
            try:
                parsed = UUID(token)
            except ValueError as e:
                raise ValueError(f"Invalid project UUID: {token}") from e
            if parsed not in seen:
                seen.add(parsed)
                uuids.append(parsed)
    return uuids


def parse_page(value: str | None, default: int = 1) -> int:
    if value is None or str(value).strip() == "":
        return default
    try:
        page = int(value)
    except (TypeError, ValueError) as e:
        raise ValueError("page must be a positive integer") from e
    if page < 1:
        raise ValueError("page must be a positive integer")
    return page


def parse_page_size(value: str | None, default: int = 20, maximum: int = 100) -> int:
    if value is None or str(value).strip() == "":
        return default
    try:
        size = int(value)
    except (TypeError, ValueError) as e:
        raise ValueError("page_size must be a positive integer") from e
    if size < 1:
        raise ValueError("page_size must be a positive integer")
    return min(size, maximum)


def parse_include_blocks(raw: str | None) -> set[str] | None:
    if raw is None or not str(raw).strip():
        return None
    blocks = {part.strip().lower() for part in str(raw).split(",") if part.strip()}
    unknown = blocks - OPTIONAL_INCLUDE_BLOCKS
    if unknown:
        raise ValueError(f"Invalid include values: {', '.join(sorted(unknown))}")
    return blocks


def _calendar_date_to_date(value: pendulum.Date) -> date:
    return date(value.year, value.month, value.day)


def _validate_metrics_earliest_date(field_name: str, value: pendulum.Date) -> None:
    day = _calendar_date_to_date(value)
    if day < CONVERSATIONS_METRICS_EARLIEST_DATE:
        raise ValueError(
            f"{field_name} must be on or after {CONVERSATIONS_METRICS_EARLIEST_DATE.isoformat()} "
            "(conversations metrics are only available from that date)"
        )


def resolve_calendar_range(
    start_date: pendulum.Date | None,
    end_date: pendulum.Date | None,
) -> tuple[pendulum.Date | None, pendulum.Date | None]:
    if start_date is None and end_date is None:
        return None, None
    if start_date is None or end_date is None:
        raise ValueError("start_date and end_date must both be provided or both omitted")
    _validate_metrics_earliest_date("start_date", start_date)
    _validate_metrics_earliest_date("end_date", end_date)
    if start_date > end_date:
        raise ValueError("start_date must be before or equal to end_date")
    return start_date, end_date


def eligible_projects_queryset(project_uuids: list[UUID] | None):
    """AB 2 projects only: inline_agent_switch=True (AB 1 uses inline_agent_switch=False)."""
    qs = Project.objects.filter(is_active=True, inline_agent_switch=True).select_related("manager_agent")
    if project_uuids:
        qs = qs.filter(uuid__in=project_uuids)
    return qs.order_by("name")


def _manager_name(project: Project) -> str:
    manager = project.manager_agent
    if manager and manager.name:
        return manager.name
    return MANAGER_FALLBACK


def _agent_counts(projects: list[Project]) -> dict[UUID, dict[str, int]]:
    if not projects:
        return {}
    rows = (
        Agent.objects.filter(project__in=projects)
        .values("project_id")
        .annotate(
            agents_count=Count("uuid"),
            official_agents_count=Count("uuid", filter=Q(is_official=True)),
        )
    )
    return {
        row["project_id"]: {
            "agents_count": int(row["agents_count"] or 0),
            "official_agents_count": int(row["official_agents_count"] or 0),
        }
        for row in rows
    }


def _metrics_by_project_uuid(summary_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["project_uuid"]): row for row in summary_payload.get("projects", [])}


def resolution_rate_from_counts(*, resolved_count: int, unresolved_count: int) -> float | None:
    """Rate from evaluable conversations only (resolved + unresolved)."""
    evaluable_count = resolved_count + unresolved_count
    if evaluable_count < 1:
        return None
    return float(resolved_count / evaluable_count)


def _period_averages_from_metric_rows(project_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Recompute period averages for a filtered project subset."""
    if not project_metrics:
        return empty_summary_averages()

    rates = [float(row["resolution_rate"]) for row in project_metrics if row.get("resolution_rate") is not None]
    if rates:
        average_resolution_rate = round(float(sum(rates) / len(rates)), 4)
    else:
        average_resolution_rate = None

    csat_den = sum(int(row.get("csat_responses_count") or 0) for row in project_metrics)
    csat_num = sum(
        float(row["csat"]) * int(row["csat_responses_count"])
        for row in project_metrics
        if row.get("csat") is not None and int(row.get("csat_responses_count") or 0) > 0
    )
    nps_den = sum(int(row.get("nps_responses_count") or 0) for row in project_metrics)
    nps_num = sum(
        float(row["nps"]) * int(row["nps_responses_count"])
        for row in project_metrics
        if row.get("nps") is not None and int(row.get("nps_responses_count") or 0) > 0
    )

    return {
        "average_resolution_rate": average_resolution_rate,
        "average_csat": round(csat_num / csat_den, 4) if csat_den else None,
        "average_nps": round(nps_num / nps_den, 4) if nps_den else None,
    }


def resolve_projects_for_response(
    *,
    query: ResolutionRateQuery,
    summary_payload: dict[str, Any],
    eligible_projects: list[Project],
) -> tuple[list[Project], dict[str, Any]]:
    """
    When project_uuids are omitted, keep only eligible AB2 projects with conversations in range.
    Period averages exclude projects without evaluable resolution data.
    """
    metrics_map = _metrics_by_project_uuid(summary_payload)

    if query.project_uuids is not None:
        projects = eligible_projects
    else:
        projects = []
        for project in eligible_projects:
            metrics = metrics_map.get(str(project.uuid))
            if not metrics:
                continue
            if int(metrics.get("conversation_count") or 0) < 1:
                continue
            projects.append(project)

    metric_rows = [metrics_map.get(str(project.uuid), {}) for project in projects]
    return projects, _period_averages_from_metric_rows(metric_rows)


def conversations_fetch_project_uuids(query: ResolutionRateQuery, eligible_projects: list[Project]) -> list[str] | None:
    """Omit UUID list when the client did not filter by project (avoids oversized query strings)."""
    if query.project_uuids is None:
        return None
    return [str(project.uuid) for project in eligible_projects]


def _resolution_rate_from_metrics(
    metrics: dict[str, Any],
    *,
    resolved_count: int,
    unresolved_count: int,
) -> float | None:
    raw = metrics.get("resolution_rate")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    return resolution_rate_from_counts(
        resolved_count=resolved_count,
        unresolved_count=unresolved_count,
    )


def _response_dates(query: ResolutionRateQuery, summary_payload: dict[str, Any]) -> tuple[Any, Any]:
    start_date = query.start_date.isoformat() if query.start_date else summary_payload.get("start_date")
    end_date = query.end_date.isoformat() if query.end_date else summary_payload.get("end_date")
    return start_date, end_date


def build_result_rows(
    projects: list[Project],
    summary_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    metrics_map = _metrics_by_project_uuid(summary_payload)
    agent_map = _agent_counts(projects)
    rows: list[dict[str, Any]] = []

    for project in projects:
        metrics = metrics_map.get(str(project.uuid), {})
        agent_row = agent_map.get(project.uuid, {"agents_count": 0, "official_agents_count": 0})
        conversation_count = int(metrics.get("conversation_count") or 0)
        resolved_count = int(metrics.get("resolved_count") or 0)
        unresolved_count = int(metrics.get("unresolved_count") or 0)
        resolution_rate = _resolution_rate_from_metrics(
            metrics,
            resolved_count=resolved_count,
            unresolved_count=unresolved_count,
        )

        rows.append(
            {
                "project_uuid": str(project.uuid),
                "project_name": project.name,
                "resolution_rate": round(resolution_rate, 4) if resolution_rate is not None else None,
                "conversation_count": conversation_count,
                "resolved_count": resolved_count,
                "unresolved_count": unresolved_count,
                "human_support_count": int(metrics.get("human_support_count") or 0),
                "csat": metrics.get("csat"),
                "csat_responses_count": int(metrics.get("csat_responses_count") or 0),
                "nps": metrics.get("nps"),
                "nps_responses_count": int(metrics.get("nps_responses_count") or 0),
                "manager": _manager_name(project),
                "uses_components": bool(project.use_components),
                "agents_count": agent_row["agents_count"],
                "official_agents_count": agent_row["official_agents_count"],
            }
        )
    return rows


def sort_result_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            row.get("resolution_rate") is None,
            -(float(row["resolution_rate"]) if row.get("resolution_rate") is not None else 0.0),
            -int(row.get("conversation_count") or 0),
            str(row.get("project_name") or "").lower(),
        ),
    )


def apply_include_blocks(row: dict[str, Any], include_blocks: set[str] | None) -> dict[str, Any]:
    if include_blocks is None:
        return row

    filtered = {
        "project_uuid": row["project_uuid"],
        "project_name": row["project_name"],
        "resolution_rate": row["resolution_rate"],
    }
    if "conversations" in include_blocks:
        for field in CONVERSATION_METRIC_FIELDS:
            filtered[field] = row[field]
    if "csat" in include_blocks:
        for field in CSAT_FIELDS:
            filtered[field] = row[field]
    if "nps" in include_blocks:
        for field in NPS_FIELDS:
            filtered[field] = row[field]
    if "manager" in include_blocks:
        filtered["manager"] = row["manager"]
    if "components" in include_blocks:
        filtered["uses_components"] = row["uses_components"]
    if "agents" in include_blocks:
        for field in AGENT_FIELDS:
            filtered[field] = row[field]
    return filtered


def paginate_rows(rows: list[dict[str, Any]], page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
    total = len(rows)
    offset = (page - 1) * page_size
    return rows[offset : offset + page_size], total


def empty_summary_averages() -> dict[str, Any]:
    return {
        "average_resolution_rate": 0.0,
        "average_csat": None,
        "average_nps": None,
    }


def build_response(
    *,
    query: ResolutionRateQuery,
    summary_payload: dict[str, Any],
    projects: list[Project],
    period_averages: dict[str, Any],
) -> dict[str, Any]:
    start_date, end_date = _response_dates(query, summary_payload)

    if not projects:
        return {
            "count": 0,
            "page": query.page,
            "page_size": query.page_size,
            "start_date": start_date,
            "end_date": end_date,
            **empty_summary_averages(),
            "results": [],
        }

    rows = sort_result_rows(build_result_rows(projects, summary_payload))
    page_rows, count = paginate_rows(rows, query.page, query.page_size)
    results = [apply_include_blocks(row, query.include_blocks) for row in page_rows]

    return {
        "count": count,
        "page": query.page,
        "page_size": query.page_size,
        "start_date": start_date,
        "end_date": end_date,
        **period_averages,
        "results": results,
    }


def log_conversations_failure(
    *,
    project_uuids: list[str],
    start_date: str | None,
    end_date: str | None,
    exc: Exception,
) -> None:
    logger.error(
        "[projects_resolution_rate] nexus-conversations request failed "
        "project_count=%s start_date=%s end_date=%s sample_project_uuids=%s",
        len(project_uuids),
        start_date,
        end_date,
        project_uuids[:5],
        exc_info=(type(exc), exc, exc.__traceback__),
    )
