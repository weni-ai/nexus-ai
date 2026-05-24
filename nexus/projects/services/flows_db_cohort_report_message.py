"""PT-BR admin email copy; English-only Sentry payloads for divergences and technical failures."""

from __future__ import annotations

import json
from typing import Any

import sentry_sdk

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
    divergent_days: list[dict[str, Any]] = []
    for day in report.get("day_summaries", []):
        bullets = day_divergence_bullets(day)
        if bullets:
            divergent_days.append(
                {
                    "day": day.get("day"),
                    "from_inclusive": day.get("from_inclusive"),
                    "to_inclusive": day.get("to_inclusive"),
                    "bullets": bullets,
                }
            )

    return {
        "recipient_email": recipient_email,
        "project_id": report.get("project_id"),
        "range_from": requested.get("from_inclusive"),
        "range_to": requested.get("to_inclusive"),
        "days_in_range": report.get("days_in_range"),
        "overall_status": report.get("overall_status"),
        "divergent_days": divergent_days,
        "has_divergences": bool(divergent_days),
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
