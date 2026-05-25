from unittest import mock

from nexus.projects.services.flows_db_cohort_report_message import (
    aggregate_period_summary_counts,
    build_email_context,
    build_failure_email_context,
    build_truncated_uuid_list,
    day_divergence_bullets,
    format_email_day_label,
    format_email_period_pt_br,
    report_has_divergences,
)


def _aligned_report():
    return {
        "project_id": "p1",
        "requested_range": {"from_inclusive": "2026-01-10T00:00:00Z", "to_inclusive": "2026-01-10T23:59:59Z"},
        "days_in_range": 1,
        "overall_status": "aligned",
        "day_summaries": [
            {
                "day": "2026-01-10",
                "status": "aligned",
                "flows_events_inside_selected_dates": 10,
                "conversations_inside_date_rules": 10,
                "matching_start_and_end_times": 10,
                "count_only_in_flows": 0,
                "count_only_in_database": 0,
            }
        ],
        "day_errors": [],
    }


def _divergent_report():
    return {
        "project_id": "p1",
        "requested_range": {"from_inclusive": "2026-01-10T00:00:00Z", "to_inclusive": "2026-01-11T23:59:59Z"},
        "days_in_range": 2,
        "overall_status": "needs_review",
        "day_summaries": [
            {
                "day": "2026-01-10",
                "status": "aligned",
                "flows_events_inside_selected_dates": 5,
                "conversations_inside_date_rules": 5,
                "matching_start_and_end_times": 5,
                "count_only_in_flows": 0,
                "count_only_in_database": 0,
            },
            {
                "day": "2026-01-11",
                "status": "needs_review",
                "flows_events_inside_selected_dates": 8,
                "conversations_inside_date_rules": 7,
                "matching_start_and_end_times": 6,
                "count_only_in_flows": 1,
                "count_only_in_database": 0,
                "ids_only_in_flows": ["aaaa-bbbb-cccc-dddd-eeeeeeeeeeee"],
                "ids_only_in_database": [],
                "ids_timestamp_differ": ["11111111-2222-3333-4444-555555555555"],
            },
        ],
        "day_errors": [],
    }


def test_report_has_divergences_false_when_aligned():
    assert report_has_divergences(_aligned_report()) is False


def test_report_has_divergences_true_when_counts_mismatch():
    assert report_has_divergences(_divergent_report()) is True


def test_day_divergence_bullets_pt_br():
    day = _divergent_report()["day_summaries"][1]
    bullets = day_divergence_bullets(day)
    assert any("só no Flows" in b for b in bullets)
    assert any("início ou fim diferente" in b for b in bullets)


@mock.patch(
    "nexus.projects.services.flows_db_cohort_report_message.fetch_project_name",
    return_value=None,
)
def test_build_email_context_lists_only_divergent_days(_mock_name):
    ctx = build_email_context(_divergent_report(), "user@example.com")
    assert ctx["has_divergences"] is True
    assert len(ctx["divergence_days"]) == 1
    assert ctx["divergence_days"][0]["calendar_day"] == "2026-01-11"
    flows_sample = ctx["divergence_days"][0]["divergent_uuid_samples"]["flows_only"]
    assert flows_sample["uuids"] == ["aaaa-bbbb-cccc-dddd-eeeeeeeeeeee"]
    assert flows_sample["total_count"] == 1
    assert flows_sample["is_truncated"] is False
    assert ctx["max_uuids_per_side_in_email"] == 10


def test_build_truncated_uuid_list_truncates_at_limit():
    ids = [f"uuid-{i:02d}" for i in range(15)]
    result = build_truncated_uuid_list(ids, max_items=10)
    assert len(result["uuids"]) == 10
    assert result["total_count"] == 15
    assert result["is_truncated"] is True


@mock.patch(
    "nexus.projects.services.flows_db_cohort_report_message.fetch_project_name",
    return_value="Projeto Teste",
)
def test_build_email_context_ok_when_aligned(_mock_name):
    ctx = build_email_context(_aligned_report(), "user@example.com")
    assert ctx["has_divergences"] is False
    assert ctx["divergence_days"] == []
    assert ctx["period_summary"]["flows_classification_events"] == 10
    assert ctx["period_summary"]["database_conversations"] == 10
    assert len(ctx["daily_rows"]) == 1
    assert ctx["daily_rows"][0]["flows_classification_events"] == 10
    assert ctx["project_name"] == "Projeto Teste"
    assert ctx["project_label"] == "Projeto Teste (p1)"
    assert ctx["formatted_period"] == "10/01/2026"
    assert ctx["daily_rows"][0]["formatted_day"] == "10/01/2026"


def test_format_email_period_pt_br_range():
    assert format_email_period_pt_br("2026-05-06T00:00:00Z", "2026-05-12T23:59:59Z") == "06/05/2026 a 12/05/2026"


def test_format_email_period_pt_br_single_day():
    assert format_email_period_pt_br("2026-05-06T00:00:00Z", "2026-05-06T23:59:59Z") == "06/05/2026"


def test_format_email_period_uses_calendar_date_not_timezone_shift():
    assert format_email_period_pt_br("2026-01-10T00:00:00Z", "2026-01-10T23:59:59Z") == "10/01/2026"


def test_format_email_day_label():
    assert format_email_day_label("2026-05-12") == "12/05/2026"


@mock.patch(
    "nexus.projects.services.flows_db_cohort_report_message.fetch_project_name",
    return_value="Loja ACME",
)
def test_build_failure_email_context(_mock_name):
    ctx = build_failure_email_context(
        recipient_email="user@example.com",
        project_id="uuid-1",
        date_start="2026-05-06T00:00:00Z",
        date_end="2026-05-12T23:59:59Z",
        error_message="erro",
    )
    assert ctx["project_label"] == "Loja ACME (uuid-1)"
    assert ctx["formatted_period"] == "06/05/2026 a 12/05/2026"


def test_aggregate_period_summary_counts_sums_days():
    totals = aggregate_period_summary_counts(_divergent_report()["day_summaries"])
    assert totals["flows_classification_events"] == 13
    assert totals["database_conversations"] == 12
    assert totals["conversations_only_in_flows"] == 1
