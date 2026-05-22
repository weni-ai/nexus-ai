from urllib.error import HTTPError, URLError

from nexus.celery import app
from nexus.projects.services.flows_db_cohort_email import (
    send_reconcile_failure_email,
    send_reconcile_success_email,
)
from nexus.projects.services.flows_db_cohort_service import run_flows_db_cohort_reconcile_range


@app.task(name="nexus.projects.tasks.reconcile_flows_db_cohort_email_task")
def reconcile_flows_db_cohort_email_task(cfg: dict, recipient_email: str):
    """Run multi-day Flows vs DB reconcile and email the aggregated report."""
    import requests

    project_id = str(cfg.get("project", ""))
    date_start = str(cfg.get("date_start", ""))
    date_end = str(cfg.get("date_end", ""))

    try:
        report = run_flows_db_cohort_reconcile_range(cfg)
        if report.get("overall_status") == "failed":
            errors = report.get("day_errors") or []
            detail = errors[0]["error"] if errors else "All days failed"
            send_reconcile_failure_email(
                recipient_email,
                project_id=project_id,
                date_start=date_start,
                date_end=date_end,
                error_message=detail,
            )
        else:
            send_reconcile_success_email(recipient_email, report)
        return report
    except (HTTPError, URLError, ValueError, requests.exceptions.RequestException) as exc:
        send_reconcile_failure_email(
            recipient_email,
            project_id=project_id,
            date_start=date_start,
            date_end=date_end,
            error_message=str(exc),
        )
        raise
    except Exception as exc:
        send_reconcile_failure_email(
            recipient_email,
            project_id=project_id,
            date_start=date_start,
            date_end=date_end,
            error_message=str(exc),
        )
        raise
