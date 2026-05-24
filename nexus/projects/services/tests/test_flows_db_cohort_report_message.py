from nexus.projects.services.flows_db_cohort_report_message import (
    build_email_context,
    day_divergence_bullets,
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


def test_build_email_context_lists_only_divergent_days():
    ctx = build_email_context(_divergent_report(), "user@example.com")
    assert ctx["has_divergences"] is True
    assert len(ctx["divergent_days"]) == 1
    assert ctx["divergent_days"][0]["day"] == "2026-01-11"


def test_build_email_context_ok_when_aligned():
    ctx = build_email_context(_aligned_report(), "user@example.com")
    assert ctx["has_divergences"] is False
    assert ctx["divergent_days"] == []
