from nexus.celery import app
from nexus.projects.services.flows_db_cohort_credentials import attach_flows_api_token
from nexus.projects.services.flows_db_cohort_email import (
    send_reconcile_failure_email,
    send_reconcile_result_email,
)
from nexus.projects.services.flows_db_cohort_job_store import (
    DELIVERY_EMAIL,
    set_job_completed,
    set_job_failed,
    set_job_running,
)
from nexus.projects.services.flows_db_cohort_service import run_flows_db_cohort_reconcile_range


def _deliver_email_result(
    *,
    recipient_email: str,
    report: dict,
    project_id: str,
    date_start: str,
    date_end: str,
    job_id: str,
) -> None:
    if report.get("overall_status") == "failed":
        errors = report.get("day_errors") or []
        detail = errors[0]["error"] if errors else "Falha em todos os dias analisados"
        send_reconcile_failure_email(
            recipient_email,
            project_id=project_id,
            date_start=date_start,
            date_end=date_end,
            error_message=detail,
            report=report,
            job_id=job_id,
        )
    else:
        send_reconcile_result_email(recipient_email, report, job_id=job_id)


@app.task(name="nexus.projects.tasks.reconcile_flows_db_cohort_email_task", bind=True)
def reconcile_flows_db_cohort_email_task(self, cfg: dict, recipient_email: str | None, delivery: str = DELIVERY_EMAIL):
    """Run multi-day Flows vs DB reconcile; deliver by email and/or store JSON for polling."""
    project_id = str(cfg.get("project", ""))
    date_start = str(cfg.get("date_start", ""))
    date_end = str(cfg.get("date_end", ""))
    job_id = str(self.request.id)
    deliver_email = delivery == DELIVERY_EMAIL and recipient_email

    set_job_running(job_id)

    try:
        cfg_with_token = attach_flows_api_token(cfg, job_id)
        report = run_flows_db_cohort_reconcile_range(cfg_with_token)
        set_job_completed(job_id, report)

        if deliver_email:
            _deliver_email_result(
                recipient_email=recipient_email,
                report=report,
                project_id=project_id,
                date_start=date_start,
                date_end=date_end,
                job_id=job_id,
            )

        return report
    except Exception as exc:
        set_job_failed(job_id, str(exc))
        if deliver_email:
            send_reconcile_failure_email(
                recipient_email,
                project_id=project_id,
                date_start=date_start,
                date_end=date_end,
                error_message=str(exc),
                job_id=job_id,
            )
        raise
