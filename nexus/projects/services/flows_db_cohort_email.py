from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from nexus.projects.services.flows_db_cohort_report_message import (
    build_email_context,
    publish_divergences_to_sentry,
    publish_technical_failure_to_sentry,
    report_has_divergences,
)

logger = logging.getLogger(__name__)


def _send_html_email(*, subject: str, to: str, template_txt: str, template_html: str, context: dict[str, Any]) -> int:
    if not getattr(settings, "SEND_EMAILS", True):
        logger.info("[flows_db_cohort] SEND_EMAILS=false; skipping email to %s subject=%s", to, subject)
        return 0

    text_content = render_to_string(template_txt, context)
    html_content = render_to_string(template_html, context)
    from_email = settings.DEFAULT_FROM_EMAIL
    msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
    msg.attach_alternative(html_content, "text/html")
    return msg.send()


def send_reconcile_result_email(
    recipient_email: str,
    report: dict[str, Any],
    *,
    job_id: str | None = None,
) -> int:
    """PT-BR admin email. Sentry is sent only when divergences exist."""
    context = build_email_context(report, recipient_email)
    prefix = getattr(settings, "EMAIL_SUBJECT_PREFIX", "")

    if report_has_divergences(report):
        publish_divergences_to_sentry(report, recipient_email=recipient_email, job_id=job_id)
        subject = f"{prefix}Reconciliação Flows x banco: divergências encontradas"
        template_txt = "flows_db_cohort/emails/reconcile_divergences.txt"
        template_html = "flows_db_cohort/emails/reconcile_divergences.html"
    else:
        subject = f"{prefix}Reconciliação Flows x banco: nenhuma divergência encontrada"
        template_txt = "flows_db_cohort/emails/reconcile_ok.txt"
        template_html = "flows_db_cohort/emails/reconcile_ok.html"

    return _send_html_email(
        subject=subject,
        to=recipient_email,
        template_txt=template_txt,
        template_html=template_html,
        context=context,
    )


def send_reconcile_failure_email(
    recipient_email: str,
    *,
    project_id: str,
    date_start: str,
    date_end: str,
    error_message: str,
    report: dict[str, Any] | None = None,
    job_id: str | None = None,
) -> int:
    publish_technical_failure_to_sentry(
        recipient_email=recipient_email,
        project_id=project_id,
        date_start=date_start,
        date_end=date_end,
        error_message=error_message,
        job_id=job_id,
        report=report,
    )
    prefix = getattr(settings, "EMAIL_SUBJECT_PREFIX", "")
    subject = f"{prefix}Reconciliação Flows x banco: falha na execução"
    context = {
        "project_id": project_id,
        "date_start": date_start,
        "date_end": date_end,
        "error_message": error_message,
        "recipient_email": recipient_email,
    }
    return _send_html_email(
        subject=subject,
        to=recipient_email,
        template_txt="flows_db_cohort/emails/reconcile_failure.txt",
        template_html="flows_db_cohort/emails/reconcile_failure.html",
        context=context,
    )
