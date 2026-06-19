"""Resolve reconcile date windows using each project's calendar timezone."""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any

import pendulum
from django.conf import settings

logger = logging.getLogger(__name__)

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_START_SENTINEL_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T00:00:00(\.0+)?(Z|[+-]00:00)?$")
_END_SENTINEL_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T23:59:59(\.\d+)?(Z|[+-]00:00)?$")


def resolve_effective_project_timezone(stored_tz: str | None) -> str:
    fallback = getattr(settings, "FALLBACK_TIMEZONE", "America/Sao_Paulo")
    if stored_tz:
        try:
            pendulum.now(stored_tz)
            return stored_tz
        except Exception:
            pass
    return fallback


def prepare_calendar_range_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    """
    For multi-day calendar requests, bootstrap project timezone from reconcile-cohort
    metadata (first day) so daily iteration can split in project-local days.
    """
    cal_range = parse_requested_calendar_range(str(cfg["date_start"]), str(cfg["date_end"]))
    if cal_range is None:
        return cfg

    cal_start, cal_end = cal_range
    if calendar_range_day_count(cal_start, cal_end) == 1:
        return cfg

    from nexus.projects.services.flows_db_cohort_service import fetch_db_cohort_export

    day = cal_start.isoformat()
    bootstrap_export = fetch_db_cohort_export(
        {
            **cfg,
            "date_start": f"{day}T00:00:00Z",
            "date_end": f"{day}T23:59:59Z",
        }
    )
    project_timezone = bootstrap_export.get("selected_date_range", {}).get("project_timezone")
    return resolve_reconcile_cfg_dates(cfg, project_timezone)


def format_reconcile_utc_instant(dt: pendulum.DateTime) -> str:
    return dt.in_timezone("UTC").format("YYYY-MM-DDTHH:mm:ss.SSSSSS[Z]")


def parse_requested_calendar_range(date_start: str, date_end: str) -> tuple[date, date] | None:
    start_raw = str(date_start).strip()
    end_raw = str(date_end).strip()

    if _DATE_ONLY_RE.match(start_raw):
        cal_start = date.fromisoformat(start_raw)
        if not _DATE_ONLY_RE.match(end_raw):
            raise ValueError("date_end must be YYYY-MM-DD when date_start is YYYY-MM-DD")
        cal_end = date.fromisoformat(end_raw)
        return cal_start, cal_end

    start_match = _START_SENTINEL_RE.match(start_raw)
    end_match = _END_SENTINEL_RE.match(end_raw)
    if start_match and end_match:
        cal_start = date.fromisoformat(start_match.group(1))
        cal_end = date.fromisoformat(end_match.group(1))
        return cal_start, cal_end

    return None


def calendar_range_day_count(cal_start: date, cal_end: date) -> int:
    return (cal_end - cal_start).days + 1


def project_day_utc_bounds(cal_day: date, tz_name: str) -> tuple[pendulum.DateTime, pendulum.DateTime]:
    start_local = pendulum.datetime(cal_day.year, cal_day.month, cal_day.day, 0, 0, 0, tz=tz_name).start_of("day")
    end_local = start_local.end_of("day")
    return start_local.in_timezone("UTC"), end_local.in_timezone("UTC")


def resolve_reconcile_cfg_dates(cfg: dict[str, Any], project_timezone: str | None) -> dict[str, Any]:
    tz_name = resolve_effective_project_timezone(project_timezone)
    cal_range = parse_requested_calendar_range(str(cfg["date_start"]), str(cfg["date_end"]))
    if cal_range is None:
        return cfg

    cal_start, cal_end = cal_range
    if cal_end < cal_start:
        raise ValueError("date_end must be on or after date_start")

    resolved = dict(cfg)
    resolved["project_timezone"] = tz_name
    resolved["_calendar_range"] = (cal_start, cal_end)
    resolved["_interpreted_as_project_calendar_days"] = True

    if cal_start == cal_end:
        start_utc, end_utc = project_day_utc_bounds(cal_start, tz_name)
        resolved["date_start"] = format_reconcile_utc_instant(start_utc)
        resolved["date_end"] = format_reconcile_utc_instant(end_utc)
        resolved["_calendar_day"] = cal_start.isoformat()
    else:
        first_start, _ = project_day_utc_bounds(cal_start, tz_name)
        _, last_end = project_day_utc_bounds(cal_end, tz_name)
        resolved["date_start"] = format_reconcile_utc_instant(first_start)
        resolved["date_end"] = format_reconcile_utc_instant(last_end)

    return resolved


def iter_project_calendar_day_cfgs(base_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    cal_range = base_cfg.get("_calendar_range")
    tz_name = base_cfg.get("project_timezone")
    if cal_range and tz_name:
        cal_start, cal_end = cal_range
        cfgs: list[dict[str, Any]] = []
        day = cal_start
        while day <= cal_end:
            start_utc, end_utc = project_day_utc_bounds(day, tz_name)
            cfg = dict(base_cfg)
            cfg["date_start"] = format_reconcile_utc_instant(start_utc)
            cfg["date_end"] = format_reconcile_utc_instant(end_utc)
            cfg["use_date_end"] = True
            cfg["_calendar_day"] = day.isoformat()
            cfgs.append(cfg)
            day += timedelta(days=1)
        return cfgs

    return []
