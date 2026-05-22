from nexus.celery import app
from nexus.projects.services.flows_db_cohort_credentials import attach_flows_api_token
from nexus.projects.services.flows_db_cohort_email import (
    send_reconcile_failure_email,
    send_reconcile_success_email,
)
from nexus.projects.services.flows_db_cohort_service import run_flows_db_cohort_reconcile_range


@app.task(name="nexus.projects.tasks.reconcile_flows_db_cohort_email_task", bind=True)
def reconcile_flows_db_cohort_email_task(self, cfg: dict, recipient_email: str):
    """Run multi-day Flows vs DB reconcile and email the aggregated report."""
    project_id = str(cfg.get("project", ""))
    date_start = str(cfg.get("date_start", ""))
    date_end = str(cfg.get("date_end", ""))

    try:
        cfg_with_token = attach_flows_api_token(cfg, self.request.id)
        report = run_flows_db_cohort_reconcile_range(cfg_with_token)
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
    except Exception as exc:
        send_reconcile_failure_email(
            recipient_email,
            project_id=project_id,
            date_start=date_start,
            date_end=date_end,
            error_message=str(exc),
        )
        raise
