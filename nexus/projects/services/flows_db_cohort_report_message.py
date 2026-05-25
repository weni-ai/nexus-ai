"""PT-BR admin email copy; English-only Sentry payloads for divergences and technical failures."""

from __future__ import annotations

import json
from typing import Any

import pendulum
import sentry_sdk

_EMAIL_TZ = "America/Sao_Paulo"

OVERALL_ALIGNED = "aligned"
OVERALL_NEEDS_REVIEW = "needs_review"
OVERALL_PARTIAL_FAILURE = "partial_failure"
OVERALL_FAILED = "failed"


def report_has_divergences(report: dict[str, Any]) -> bool:
    """True when the range is not fully aligned (business divergences or day errors)."""
    overall = report.get("overall_status")
    if overall in (OVERALL_NEEDS_REVIEW, OVERALL_PARTIAL_FAILURE):
        return True
    for day in report.get("day_summaries", []):
        if day.get("status") in ("needs_review", "error"):
            return True
        if int(day.get("count_only_in_flows", 0)) > 0 or int(day.get("count_only_in_database", 0)) > 0:
            return True
        flows = int(day.get("flows_events_inside_selected_dates", 0))
        matching = int(day.get("matching_start_and_end_times", 0))
        if flows > matching:
            return True
    return False


def format_email_day_label(day: str | None) -> str:
    """Calendar day label for emails (PT-BR short date, no UTC day shift)."""
    if not day:
        return ""
    raw = str(day).strip()[:10]
    year, month, day_of_month = (int(part) for part in raw.split("-"))
    return pendulum.datetime(year, month, day_of_month, tz=_EMAIL_TZ).format("DD/MM/YYYY")


def format_email_period_pt_br(from_inclusive: str | None, to_inclusive: str | None) -> str:
    """Human-friendly period for admin emails (PT-BR, calendar dates from the request)."""
    if not from_inclusive or not to_inclusive:
        return ""
    start_label = format_email_day_label(str(from_inclusive).strip()[:10])
    end_label = format_email_day_label(str(to_inclusive).strip()[:10])
    if start_label == end_label:
        return start_label
    return f"{start_label} a {end_label}"


def fetch_project_name(project_id: str) -> str | None:
    """Load project display name from nexus-ai (Celery worker has Django ORM)."""
    from nexus.projects.models import Project

    row = Project.objects.filter(uuid=project_id).values("name").first()
    if row and row.get("name"):
        return str(row["name"]).strip() or None
    return None


def resolve_project_email_fields(project_id: str | None) -> dict[str, str | None]:
    """Load project name from nexus-ai DB; fall back to UUID only."""
    pid = str(project_id or "").strip()
    if not pid:
        return {"project_uuid": "", "project_name": None, "project_label": ""}

    project_name: str | None = None
    try:
        project_name = fetch_project_name(pid)
    except Exception:
        project_name = None

    label = f"{project_name} ({pid})" if project_name else pid
    return {"project_uuid": pid, "project_name": project_name, "project_label": label}


def build_daily_comparison_row(day: dict[str, Any]) -> dict[str, Any]:
    """Per-day counts for admin emails (Flows events vs DB cohort)."""
    calendar_day = day.get("day")
    return {
        "calendar_day": calendar_day,
        "formatted_day": format_email_day_label(calendar_day),
        "reconcile_status": day.get("status"),
        "flows_classification_events": int(day.get("flows_events_inside_selected_dates", 0)),
        "database_conversations": int(day.get("conversations_inside_date_rules", 0)),
        "conversations_only_in_flows": int(day.get("count_only_in_flows", 0)),
        "conversations_only_in_database": int(day.get("count_only_in_database", 0)),
        "error_message": day.get("error"),
    }


def _sorted_unique_ids(values: list[str]) -> list[str]:
    return sorted({str(v).strip() for v in values if v})


def max_uuids_per_side_in_email() -> int:
    try:
        from django.conf import settings as django_settings

        return int(getattr(django_settings, "FLOWS_DB_COHORT_EMAIL_UUID_SAMPLE_LIMIT", 10))
    except Exception:
        return 10


def build_truncated_uuid_list(conversation_uuids: list[str], *, max_items: int | None = None) -> dict[str, Any]:
    """UUID list for admin email with total count when truncated."""
    cap = max_uuids_per_side_in_email() if max_items is None else max_items
    ordered = _sorted_unique_ids(conversation_uuids)
    total_count = len(ordered)
    return {
        "uuids": ordered[:cap],
        "total_count": total_count,
        "is_truncated": total_count > cap,
        "max_items": cap,
    }


def build_period_divergent_uuid_samples(day_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    """Divergent conversation UUID samples for the whole period (max per side)."""
    flows_only_uuids: list[str] = []
    database_only_uuids: list[str] = []
    for day in day_summaries:
        if day.get("status") == "error":
            continue
        flows_only_uuids.extend(day.get("ids_only_in_flows") or [])
        database_only_uuids.extend(day.get("ids_only_in_database") or [])
    return {
        "flows_only": build_truncated_uuid_list(flows_only_uuids),
        "database_only": build_truncated_uuid_list(database_only_uuids),
    }


def build_daily_divergent_uuid_samples(day: dict[str, Any]) -> dict[str, Any]:
    """Divergent conversation UUID samples for one calendar day (max per side)."""
    return {
        "flows_only": build_truncated_uuid_list(list(day.get("ids_only_in_flows") or [])),
        "database_only": build_truncated_uuid_list(list(day.get("ids_only_in_database") or [])),
    }


def aggregate_period_summary_counts(day_summaries: list[dict[str, Any]]) -> dict[str, int]:
    """Sum reconcile counts across days that completed (exclude error rows)."""
    rows = [build_daily_comparison_row(d) for d in day_summaries if d.get("status") != "error"]
    return {
        "flows_classification_events": sum(r["flows_classification_events"] for r in rows),
        "database_conversations": sum(r["database_conversations"] for r in rows),
        "conversations_only_in_flows": sum(r["conversations_only_in_flows"] for r in rows),
        "conversations_only_in_database": sum(r["conversations_only_in_database"] for r in rows),
    }


def day_divergence_bullets(day: dict[str, Any]) -> list[str]:
    """Human-readable divergence lines for one day (PT-BR)."""
    if day.get("status") == "error":
        return [f"Falha na análise: {day.get('error', 'erro desconhecido')}"]

    bullets: list[str] = []
    only_flows = int(day.get("count_only_in_flows", 0))
    only_db = int(day.get("count_only_in_database", 0))
    flows = int(day.get("flows_events_inside_selected_dates", 0))
    matching = int(day.get("matching_start_and_end_times", 0))
    db_count = int(day.get("conversations_inside_date_rules", 0))

    if only_flows > 0:
        bullets.append(f"{only_flows} conversa(s) presente(s) só no Flows")
    if only_db > 0:
        bullets.append(f"{only_db} conversa(s) presente(s) só no banco")
    if flows > matching:
        bullets.append(
            f"{flows - matching} conversa(s) com início ou fim diferente entre Flows e banco "
            f"({matching} de {flows} com horários iguais)"
        )
    if not bullets and day.get("status") == "needs_review":
        bullets.append(f"Revisão necessária — Flows: {flows} evento(s), banco: {db_count} conversa(s)")
    return bullets


def build_email_context(report: dict[str, Any], recipient_email: str) -> dict[str, Any]:
    """Template context for admin-facing reconcile emails (PT-BR)."""
    requested = report.get("requested_range") or {}
    divergence_days: list[dict[str, Any]] = []
    for day in report.get("day_summaries", []):
        summary_lines = day_divergence_bullets(day)
        if summary_lines:
            calendar_day = day.get("day")
            divergence_days.append(
                {
                    "calendar_day": calendar_day,
                    "formatted_day": format_email_day_label(calendar_day),
                    "window_start_iso": day.get("from_inclusive"),
                    "window_end_iso": day.get("to_inclusive"),
                    "summary_lines": summary_lines,
                    "divergent_uuid_samples": build_daily_divergent_uuid_samples(day),
                }
            )

    day_summaries = report.get("day_summaries") or []
    daily_rows = [build_daily_comparison_row(d) for d in day_summaries]
    period_summary = aggregate_period_summary_counts(day_summaries)
    project_fields = resolve_project_email_fields(report.get("project_id"))
    period_start_iso = requested.get("from_inclusive")
    period_end_iso = requested.get("to_inclusive")

    return {
        "recipient_email": recipient_email,
        **project_fields,
        "period_start_iso": period_start_iso,
        "period_end_iso": period_end_iso,
        "formatted_period": format_email_period_pt_br(period_start_iso, period_end_iso),
        "days_analyzed": report.get("days_in_range"),
        "overall_status": report.get("overall_status"),
        "divergence_days": divergence_days,
        "has_divergences": bool(divergence_days),
        "period_summary": period_summary,
        "daily_rows": daily_rows,
        "period_divergent_uuid_samples": build_period_divergent_uuid_samples(day_summaries),
        "max_uuids_per_side_in_email": max_uuids_per_side_in_email(),
    }


def build_failure_email_context(
    *,
    recipient_email: str,
    project_id: str,
    date_start: str,
    date_end: str,
    error_message: str,
) -> dict[str, Any]:
    """Template context for technical-failure reconcile emails (PT-BR)."""
    project_fields = resolve_project_email_fields(project_id)
    return {
        "recipient_email": recipient_email,
        **project_fields,
        "period_start_iso": date_start,
        "period_end_iso": date_end,
        "formatted_period": format_email_period_pt_br(date_start, date_end),
        "error_message": error_message,
    }


def _apply_sentry_scope(
    scope,
    *,
    project_id: str,
    recipient_email: str,
    job_id: str | None,
    overall_status: str,
) -> None:
    scope.set_tag("flows_db_cohort", "true")
    scope.set_tag("project_id", project_id)
    scope.set_tag("flows_db_cohort_overall_status", overall_status)
    if job_id:
        scope.set_tag("flows_db_cohort_job_id", job_id)
    scope.set_extra("recipient_email", recipient_email)


def publish_divergences_to_sentry(
    report: dict[str, Any],
    *,
    recipient_email: str,
    job_id: str | None = None,
) -> None:
    """Full JSON report to Sentry when business divergences exist (English only)."""
    project_id = str(report.get("project_id", ""))
    overall = str(report.get("overall_status", "unknown"))

    with sentry_sdk.push_scope() as scope:
        _apply_sentry_scope(
            scope,
            project_id=project_id,
            recipient_email=recipient_email,
            job_id=job_id,
            overall_status=overall,
        )
        scope.set_context(
            "flows_db_cohort_report",
            {
                "overall_status": overall,
                "days_in_range": report.get("days_in_range"),
                "requested_range": report.get("requested_range"),
                "day_summaries": report.get("day_summaries"),
                "day_errors": report.get("day_errors"),
                "report_json": json.dumps(report, indent=2, default=str),
            },
        )
        sentry_sdk.capture_message(
            f"Flows vs database cohort reconcile: divergences found (project {project_id}, status={overall})",
            level="warning",
        )


def publish_technical_failure_to_sentry(
    *,
    recipient_email: str,
    project_id: str,
    date_start: str,
    date_end: str,
    error_message: str,
    job_id: str | None = None,
    report: dict[str, Any] | None = None,
) -> None:
    """Technical failure payload to Sentry (English only)."""
    with sentry_sdk.push_scope() as scope:
        _apply_sentry_scope(
            scope,
            project_id=project_id,
            recipient_email=recipient_email,
            job_id=job_id,
            overall_status=OVERALL_FAILED,
        )
        context: dict[str, Any] = {
            "error_message": error_message,
            "requested_range": {
                "from_inclusive": date_start,
                "to_inclusive": date_end,
            },
        }
        if report is not None:
            context["overall_status"] = report.get("overall_status")
            context["days_in_range"] = report.get("days_in_range")
            context["day_summaries"] = report.get("day_summaries")
            context["day_errors"] = report.get("day_errors")
            context["report_json"] = json.dumps(report, indent=2, default=str)

        scope.set_context("flows_db_cohort_report", context)
        sentry_sdk.capture_message(
            f"Flows vs database cohort reconcile: technical failure (project {project_id})",
            level="error",
        )
