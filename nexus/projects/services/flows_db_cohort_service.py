from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

import pendulum
from django.conf import settings

from nexus.internals.conversations import ConversationsRESTClient

logger = logging.getLogger(__name__)

MAX_RECONCILE_DAY_SECONDS = 86_400
FLOWS_EVENTS_PATH = "/api/v2/events.json"


def _flows_events_url() -> str:
    """Build events API URL from ``FLOWS_REST_ENDPOINT`` (same base as other Flows clients)."""
    base = str(getattr(settings, "FLOWS_REST_ENDPOINT", "") or "").rstrip("/")
    if not base:
        base = "https://flows.weni.ai"
    return f"{base}{FLOWS_EVENTS_PATH}"


def _http_timeout() -> int:
    return int(getattr(settings, "FLOWS_DB_COHORT_HTTP_TIMEOUT", 300))


def _format_api_instant(dt: pendulum.DateTime) -> str:
    return dt.in_timezone("UTC").format("YYYY-MM-DDTHH:mm:ss[Z]")


def validate_reconcile_window_seconds(start_bound: pendulum.DateTime, end_bound: pendulum.DateTime) -> None:
    if end_bound < start_bound:
        raise ValueError("date_end must be on or after date_start")
    span_seconds = end_bound.diff(start_bound).in_seconds()
    if span_seconds > MAX_RECONCILE_DAY_SECONDS:
        raise ValueError(
            f"Date window must not exceed {MAX_RECONCILE_DAY_SECONDS} seconds (one day); got {int(span_seconds)}"
        )


def reconcile_calendar_day_count(start_bound: pendulum.DateTime, end_bound: pendulum.DateTime) -> int:
    return end_bound.start_of("day").diff(start_bound.start_of("day")).in_days() + 1


def validate_reconcile_date_range(
    start_bound: pendulum.DateTime,
    end_bound: pendulum.DateTime,
    max_days: int,
) -> None:
    if end_bound < start_bound:
        raise ValueError("date_end must be on or after date_start")
    day_count = reconcile_calendar_day_count(start_bound, end_bound)
    if day_count > max_days:
        raise ValueError(f"Date range spans {day_count} days; maximum is {max_days}")


def is_single_calendar_day_range(start_bound: pendulum.DateTime, end_bound: pendulum.DateTime) -> bool:
    return reconcile_calendar_day_count(start_bound, end_bound) == 1


def parse_api_utc(s: str) -> pendulum.DateTime:
    raw = str(s).strip()
    if not raw:
        raise ValueError("empty datetime")
    try:
        return pendulum.parse(raw, tz="UTC").in_timezone("UTC")
    except Exception as e:
        raise ValueError(f"bad datetime: {s}") from e


def parse_meta_dt(s: str | None) -> pendulum.DateTime | None:
    if not s:
        return None
    try:
        return parse_api_utc(str(s))
    except ValueError:
        logger.warning("[flows_db_cohort] Malformed Flows metadata datetime: %r", s)
        return None


def window_pendulum(cfg: dict[str, Any]) -> tuple[pendulum.DateTime, pendulum.DateTime | None]:
    su = parse_api_utc(cfg["date_start"])
    if cfg.get("use_date_end", True):
        return su, parse_api_utc(cfg["date_end"])
    return su, None


def pendulum_in_window(p: pendulum.DateTime | None, su: pendulum.DateTime, eu: pendulum.DateTime | None) -> bool:
    if p is None:
        return False
    if eu is None:
        return su <= p
    return su <= p <= eu


def event_metadata_both_in_window(ev: dict[str, Any], cfg: dict[str, Any]) -> bool:
    meta = ev.get("metadata")
    if not isinstance(meta, dict):
        return False
    ms = parse_meta_dt(meta.get("conversation_start_date"))
    me = parse_meta_dt(meta.get("conversation_end_date"))
    if ms is None or me is None:
        return False
    su, eu = window_pendulum(cfg)
    return pendulum_in_window(ms, su, eu) and pendulum_in_window(me, su, eu)


def load_db_cohort_from_export(
    export: dict[str, Any],
    *,
    flow_uuids_for_timestamps: set[str] | None = None,
) -> tuple[set[str], dict[str, tuple[str | None, str | None]]]:
    db_uuids: set[str] = set()
    conv_by_lower: dict[str, tuple[str | None, str | None]] = {}
    need_dates = flow_uuids_for_timestamps or set()

    for row in export.get("conversations", []):
        key = str(row["uuid"]).lower()
        db_uuids.add(key)
        if key in need_dates:
            conv_by_lower[key] = (row.get("start_date"), row.get("end_date"))

    return db_uuids, conv_by_lower


def fetch_db_cohort_export(
    cfg: dict[str, Any],
    *,
    client: ConversationsRESTClient | None = None,
) -> dict[str, Any]:
    rest = client or ConversationsRESTClient()
    return rest.get_reconcile_cohort(
        str(cfg["project"]),
        date_start=cfg["date_start"],
        date_end=cfg["date_end"],
        apply_terminal_cohort_filter=bool(cfg.get("apply_terminal_cohort_filter", True)),
        timeout=_http_timeout(),
    )


def events_list_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("results", "events", "data", "objects"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


def _validate_flows_pagination_params(cfg: dict[str, Any]) -> tuple[str, int, int, int | None]:
    token = (cfg.get("flows_api_token") or "").strip()
    if not token:
        raise ValueError("flows_api_token is required")
    limit = int(cfg.get("flows_page_limit", 10_000))
    if limit < 1:
        raise ValueError("flows_page_limit must be >= 1")
    offset = int(cfg.get("flows_offset_start", 0))
    if offset < 0:
        raise ValueError("flows_offset_start must be >= 0")
    max_pages = cfg.get("flows_max_pages")
    if max_pages is not None:
        max_pages = int(max_pages)
        if max_pages < 1:
            raise ValueError("flows_max_pages must be >= 1 when set")
    return token, limit, offset, max_pages


def _read_flows_events_page(url: str, req: Request) -> list[Any]:
    try:
        with urlopen(req, timeout=_http_timeout()) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(
                "[flows_db_cohort] Invalid JSON from Flows url=%s response_bytes=%s",
                url,
                len(raw),
            )
            raise URLError(f"Invalid JSON response from Flows: {e}") from e
    except HTTPError as e:
        if e.fp:
            e.read()
        logger.warning("[flows_db_cohort] HTTPError %s url=%s", e.code, url)
        raise
    except URLError as e:
        logger.warning("[flows_db_cohort] URLError url=%s err=%s", url, e)
        raise
    return events_list_from_payload(payload)


def _collect_flow_cohort_pages(
    *,
    cfg: dict[str, Any],
    base_params: dict[str, Any],
    flows_base_url: str,
    auth_prefix: str,
    token: str,
    limit: int,
    offset: int,
    max_pages: int | None,
    key_name: str,
) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
    cohort: list[dict[str, Any]] = []
    total_from_api = 0
    events_with_key = 0
    page_idx = 0
    cur_offset = offset
    while True:
        if max_pages is not None and page_idx >= max_pages:
            logger.warning("[flows_db_cohort] stopped at flows_max_pages=%s", max_pages)
            break
        params = dict(base_params)
        params["offset"] = cur_offset
        url = flows_base_url + "?" + urlencode(params)
        req = Request(
            url,
            headers={
                "Authorization": f"{auth_prefix} {token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        chunk = _read_flows_events_page(url, req)
        if not chunk:
            break
        for event in chunk:
            total_from_api += 1
            if not isinstance(event, dict) or event.get("key") != key_name:
                continue
            events_with_key += 1
            if event_metadata_both_in_window(event, cfg):
                cohort.append(event)
        page_idx += 1
        if len(chunk) < limit:
            break
        cur_offset += limit
    counts = {
        "flows_events_total_from_api": total_from_api,
        "flows_events_with_this_type": events_with_key,
        "flows_events_inside_selected_dates": len(cohort),
    }
    return cohort, page_idx, counts


def fetch_flows_cohort(cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    token, limit, offset, max_pages = _validate_flows_pagination_params(cfg)
    key_name = cfg.get("key", "conversation_classification")
    base_params: dict[str, Any] = {
        "date_start": cfg["date_start"],
        "project": str(cfg["project"]),
        "key": key_name,
        "limit": limit,
    }
    if cfg.get("use_date_end", True):
        base_params["date_end"] = cfg["date_end"]

    flows_base_url = _flows_events_url()
    auth_prefix = (cfg.get("authorization_prefix") or "Token").strip()

    cohort, page_idx, counts = _collect_flow_cohort_pages(
        cfg=cfg,
        base_params=base_params,
        flows_base_url=flows_base_url,
        auth_prefix=auth_prefix,
        token=token,
        limit=limit,
        offset=offset,
        max_pages=max_pages,
        key_name=key_name,
    )

    stats: dict[str, Any] = {
        "flows_api_pages_read": page_idx,
        "flows_events_total_from_api": counts["flows_events_total_from_api"],
        "flows_event_type": key_name,
        "flows_events_with_this_type": counts["flows_events_with_this_type"],
        "flows_events_inside_selected_dates": counts["flows_events_inside_selected_dates"],
        "flows_request_url_base": flows_base_url,
    }
    if key_name == "conversation_classification":
        stats["flows_classification_event_count"] = counts["flows_events_with_this_type"]
    return cohort, stats


def build_db_cohort_summary(export: dict[str, Any]) -> dict[str, Any]:
    return {
        "conversations_inside_date_rules": export.get("conversations_inside_date_rules", 0),
        "date_matching_rule_description": export.get(
            "date_matching_rule_description",
            "both_conversation_start_and_end_inside_config_window",
        ),
        "resolution_filter_applied": export.get("resolution_filter_applied", True),
    }


def detail_compare_flows_to_db(  # noqa: C901
    events: list[dict[str, Any]],
    cfg: dict[str, Any],
    mismatch_sample_limit: int,
    *,
    conv_by_lower: dict[str, tuple[str | None, str | None]],
) -> tuple[dict[str, int], list[dict[str, Any]], list[str]]:
    stats: dict[str, int] = {
        "conversations_compared": len(events),
        "not_found_in_database": 0,
        "invalid_conversation_id_in_flows": 0,
        "unreadable_flows_metadata": 0,
        "matching_start_times": 0,
        "different_start_times": 0,
        "matching_end_times": 0,
        "different_end_times": 0,
        "matching_start_and_end_times": 0,
        "missing_conversation_id_in_flows": 0,
    }
    mismatches: list[dict[str, Any]] = []
    ids_timestamp_differ: list[str] = []

    rows: list[tuple[dict[str, Any], dict[str, Any], UUID]] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        meta = ev.get("metadata")
        if not isinstance(meta, dict):
            stats["unreadable_flows_metadata"] += 1
            continue
        u = meta.get("conversation_uuid")
        if not u:
            stats["missing_conversation_id_in_flows"] += 1
            continue
        try:
            uid = UUID(str(u))
        except (ValueError, TypeError, AttributeError):
            stats["invalid_conversation_id_in_flows"] += 1
            if len(mismatches) < mismatch_sample_limit:
                mismatches.append({"conversation_id": str(u), "reason": "invalid_conversation_id"})
            continue
        rows.append((ev, meta, uid))

    for _ev, meta, uid in rows:
        conv_dates = conv_by_lower.get(str(uid).lower())
        if conv_dates is None:
            stats["not_found_in_database"] += 1
            if len(mismatches) < mismatch_sample_limit:
                mismatches.append({"conversation_id": str(uid), "reason": "not_found_in_database"})
            continue

        db_start_raw, db_end_raw = conv_dates
        u = str(uid)
        api_start = parse_meta_dt(meta.get("conversation_start_date"))
        api_end = parse_meta_dt(meta.get("conversation_end_date"))
        db_start = parse_meta_dt(db_start_raw)
        db_end = parse_meta_dt(db_end_raw)

        sm = api_start is not None and db_start is not None and api_start == db_start
        em = api_end is not None and db_end is not None and api_end == db_end
        if api_start is None or db_start is None:
            stats["different_start_times"] += 1
            sm_ok = False
        else:
            stats["matching_start_times" if sm else "different_start_times"] += 1
            sm_ok = sm
        if api_end is None or db_end is None:
            stats["different_end_times"] += 1
            em_ok = False
        else:
            stats["matching_end_times" if em else "different_end_times"] += 1
            em_ok = em
        if sm_ok and em_ok:
            stats["matching_start_and_end_times"] += 1
        elif not (sm_ok and em_ok):
            ids_timestamp_differ.append(u)
            if len(mismatches) < mismatch_sample_limit:
                mismatches.append(
                    {
                        "conversation_id": u,
                        "flows_start_time": meta.get("conversation_start_date"),
                        "database_start_time": db_start_raw,
                        "flows_end_time": meta.get("conversation_end_date"),
                        "database_end_time": db_end_raw,
                    }
                )

    return stats, mismatches, sorted(ids_timestamp_differ)


def _flow_uuids_from_events(events: list[dict[str, Any]]) -> set[str]:
    flow_uuids: set[str] = set()
    for ev in events:
        if not isinstance(ev, dict):
            continue
        meta = ev.get("metadata")
        if not isinstance(meta, dict):
            continue
        u = meta.get("conversation_uuid")
        if u:
            flow_uuids.add(str(u).lower())
    return flow_uuids


def bidirectional_uuid_sets(
    events: list[dict[str, Any]],
    db_uuids: set[str],
    uuid_sample_limit: int,
) -> dict[str, Any]:
    flow_uuids = _flow_uuids_from_events(events)
    in_flows_not_in_db = sorted(flow_uuids - db_uuids)
    in_db_not_in_flows = sorted(db_uuids - flow_uuids)
    return {
        "unique_ids_in_flows_cohort": len(flow_uuids),
        "unique_ids_in_database_cohort": len(db_uuids),
        "count_only_in_flows": len(in_flows_not_in_db),
        "count_only_in_database": len(in_db_not_in_flows),
        "ids_only_in_flows": in_flows_not_in_db,
        "ids_only_in_database": in_db_not_in_flows,
        "example_ids_only_in_flows": in_flows_not_in_db[:uuid_sample_limit],
        "example_ids_only_in_database": in_db_not_in_flows[:uuid_sample_limit],
    }


def iter_daily_reconcile_cfgs(base_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    range_start = parse_api_utc(base_cfg["date_start"])
    range_end = parse_api_utc(base_cfg["date_end"])
    cfgs: list[dict[str, Any]] = []
    day = range_start.start_of("day")
    last_day = range_end.start_of("day")
    while day <= last_day:
        day_start = max(day, range_start)
        day_end = min(day.end_of("day"), range_end)
        cfg = dict(base_cfg)
        cfg["date_start"] = _format_api_instant(day_start)
        cfg["date_end"] = _format_api_instant(day_end)
        cfg["use_date_end"] = True
        validate_reconcile_window_seconds(parse_api_utc(cfg["date_start"]), parse_api_utc(cfg["date_end"]))
        cfgs.append(cfg)
        day = day.add(days=1)
    return cfgs


def classify_day_result(day_result: dict[str, Any]) -> str:
    ts = day_result.get("timestamp_comparison", {}).get("totals", {})
    ids = day_result.get("id_comparison_between_flows_and_database", {})
    compared = int(ts.get("conversations_compared", 0))
    db_in = int(day_result.get("database_results", {}).get("conversations_inside_date_rules", 0))
    if compared == 0 and db_in == 0:
        return "no_data"
    both_match = int(ts.get("matching_start_and_end_times", 0))
    if (
        compared > 0
        and both_match == compared
        and int(ids.get("count_only_in_flows", 0)) == 0
        and int(ids.get("count_only_in_database", 0)) == 0
        and int(ts.get("not_found_in_database", 0)) == 0
        and int(ts.get("invalid_conversation_id_in_flows", 0)) == 0
        and len(day_result.get("timestamp_comparison", {}).get("examples_where_timestamps_differ", [])) == 0
    ):
        return "aligned"
    return "needs_review"


def run_flows_db_cohort_reconcile(cfg: dict[str, Any]) -> dict[str, Any]:
    mismatch_sample_limit = int(cfg.get("mismatch_sample_limit", 20))
    uuid_sample_limit = int(cfg.get("uuid_sample_limit", 20))

    cohort, fetch_stats = fetch_flows_cohort(cfg)
    flow_uuids = _flow_uuids_from_events(cohort)
    export = fetch_db_cohort_export(cfg)
    db_uuids, conv_by_lower = load_db_cohort_from_export(export, flow_uuids_for_timestamps=flow_uuids)
    database_totals = build_db_cohort_summary(export)
    stats, mismatches, ids_timestamp_differ = detail_compare_flows_to_db(
        cohort, cfg, mismatch_sample_limit, conv_by_lower=conv_by_lower
    )
    bidir = bidirectional_uuid_sets(cohort, db_uuids, uuid_sample_limit)

    return {
        "project_id": str(cfg["project"]),
        "selected_date_range": {
            "from_inclusive": cfg["date_start"],
            "to_inclusive": cfg["date_end"] if cfg.get("use_date_end", True) else None,
            "applies_end_date_cutoff": bool(cfg.get("use_date_end", True)),
        },
        "flows_service_results": fetch_stats,
        "database_results": database_totals,
        "timestamp_comparison": {
            "totals": stats,
            "examples_where_timestamps_differ": mismatches,
        },
        "id_comparison_between_flows_and_database": bidir,
        "ids_timestamp_differ": ids_timestamp_differ,
    }


def run_flows_db_cohort_reconcile_range(base_cfg: dict[str, Any]) -> dict[str, Any]:
    daily_cfgs = iter_daily_reconcile_cfgs(base_cfg)
    day_reports: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for day_cfg in daily_cfgs:
        day_label = day_cfg["date_start"][:10]
        try:
            result = run_flows_db_cohort_reconcile(day_cfg)
            status = classify_day_result(result)
            day_reports.append(
                {
                    "day": day_label,
                    "status": status,
                    "from_inclusive": day_cfg["date_start"],
                    "to_inclusive": day_cfg["date_end"],
                    "flows_events_inside_selected_dates": result["flows_service_results"][
                        "flows_events_inside_selected_dates"
                    ],
                    "conversations_inside_date_rules": result["database_results"]["conversations_inside_date_rules"],
                    "matching_start_and_end_times": result["timestamp_comparison"]["totals"][
                        "matching_start_and_end_times"
                    ],
                    "count_only_in_flows": result["id_comparison_between_flows_and_database"]["count_only_in_flows"],
                    "count_only_in_database": result["id_comparison_between_flows_and_database"][
                        "count_only_in_database"
                    ],
                    "ids_only_in_flows": result["id_comparison_between_flows_and_database"]["ids_only_in_flows"],
                    "ids_only_in_database": result["id_comparison_between_flows_and_database"]["ids_only_in_database"],
                    "ids_timestamp_differ": result.get("ids_timestamp_differ", []),
                }
            )
        except Exception as exc:
            logger.exception("[flows_db_cohort] Day %s failed", day_label)
            errors.append({"day": day_label, "error": str(exc)})
            day_reports.append(
                {
                    "day": day_label,
                    "status": "error",
                    "from_inclusive": day_cfg["date_start"],
                    "to_inclusive": day_cfg["date_end"],
                    "error": str(exc),
                }
            )

    statuses = {r["status"] for r in day_reports}
    if errors:
        overall = "partial_failure" if len(errors) < len(daily_cfgs) else "failed"
    elif statuses <= {"aligned", "no_data"}:
        overall = "aligned"
    else:
        overall = "needs_review"

    return {
        "project_id": str(base_cfg["project"]),
        "requested_range": {
            "from_inclusive": base_cfg["date_start"],
            "to_inclusive": base_cfg["date_end"],
        },
        "days_in_range": len(daily_cfgs),
        "overall_status": overall,
        "day_summaries": day_reports,
        "day_errors": errors,
    }
