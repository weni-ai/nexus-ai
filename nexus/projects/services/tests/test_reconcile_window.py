from datetime import date

from nexus.projects.services.reconcile_window import (
    parse_requested_calendar_range,
    project_day_utc_bounds,
    resolve_reconcile_cfg_dates,
)


class TestParseRequestedCalendarRange:
    def test_parses_utc_midnight_sentinels_as_calendar_days(self):
        assert parse_requested_calendar_range(
            "2026-06-14T00:00:00Z",
            "2026-06-14T23:59:59Z",
        ) == (date(2026, 6, 14), date(2026, 6, 14))

    def test_parses_date_only_range(self):
        assert parse_requested_calendar_range("2026-06-14", "2026-06-16") == (
            date(2026, 6, 14),
            date(2026, 6, 16),
        )

    def test_returns_none_for_explicit_utc_instants(self):
        assert (
            parse_requested_calendar_range(
                "2026-06-14T03:00:00Z",
                "2026-06-15T02:59:59Z",
            )
            is None
        )


class TestResolveReconcileCfgDates:
    def test_rewrites_single_calendar_day_using_project_timezone(self):
        cfg = {
            "project": "385c8443-249e-462e-a287-f4a0dc292915",
            "date_start": "2026-06-14T00:00:00Z",
            "date_end": "2026-06-14T23:59:59Z",
        }
        resolved = resolve_reconcile_cfg_dates(cfg, "America/Sao_Paulo")

        start_utc, end_utc = project_day_utc_bounds(date(2026, 6, 14), "America/Sao_Paulo")
        assert resolved["date_start"] == start_utc.in_timezone("UTC").format("YYYY-MM-DDTHH:mm:ss.SSSSSS[Z]")
        assert resolved["date_end"] == end_utc.in_timezone("UTC").format("YYYY-MM-DDTHH:mm:ss.SSSSSS[Z]")
        assert resolved["project_timezone"] == "America/Sao_Paulo"
        assert resolved["_calendar_range"] == (date(2026, 6, 14), date(2026, 6, 14))

    def test_leaves_explicit_utc_window_unchanged(self):
        cfg = {
            "project": "385c8443-249e-462e-a287-f4a0dc292915",
            "date_start": "2026-06-14T03:00:00Z",
            "date_end": "2026-06-15T02:59:59.999999Z",
        }
        resolved = resolve_reconcile_cfg_dates(cfg, "America/Sao_Paulo")
        assert resolved["date_start"] == cfg["date_start"]
        assert resolved["date_end"] == cfg["date_end"]
