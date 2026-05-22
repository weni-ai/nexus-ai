from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

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


def send_reconcile_success_email(recipient_email: str, report: dict[str, Any]) -> int:
    prefix = getattr(settings, "EMAIL_SUBJECT_PREFIX", "")
    subject = f"{prefix}Flows vs database reconcile finished ({report.get('overall_status', 'unknown')})"
    context = {
        "report": report,
        "report_json": json.dumps(report, indent=2, default=str),
        "recipient_email": recipient_email,
    }
    return _send_html_email(
        subject=subject,
        to=recipient_email,
        template_txt="flows_db_cohort/emails/reconcile_success.txt",
        template_html="flows_db_cohort/emails/reconcile_success.html",
        context=context,
    )


def send_reconcile_failure_email(
    recipient_email: str,
    *,
    project_id: str,
    date_start: str,
    date_end: str,
    error_message: str,
) -> int:
    prefix = getattr(settings, "EMAIL_SUBJECT_PREFIX", "")
    subject = f"{prefix}Flows vs database reconcile failed"
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
