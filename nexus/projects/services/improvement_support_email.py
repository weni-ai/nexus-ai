from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import EmailMessage, get_connection

logger = logging.getLogger(__name__)

CONSOLE_EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


def _format_affected_instructions(instructions: list[dict[str, Any]]) -> str:
    if not instructions:
        return "  (none)"

    lines = []
    for instruction in instructions:
        lines.append(
            "  - instruction_id={instruction_id}, change_type={change_type}, was_changed={was_changed}".format(
                instruction_id=instruction["instruction_id"],
                change_type=instruction["change_type"],
                was_changed=str(instruction["was_changed"]).lower(),
            )
        )
    return "\n".join(lines)


def _format_affected_conversations(conversations: list[dict[str, Any]]) -> str:
    if not conversations:
        return "(none)"

    lines = []
    for index, conversation in enumerate(conversations, start=1):
        started_at = conversation["started_at"]
        if hasattr(started_at, "isoformat"):
            started_at = started_at.isoformat().replace("+00:00", "Z")

        lines.extend(
            [
                f"{index}. UUID: {conversation['uuid']}",
                f"   Contact: {conversation['contact_name']} ({conversation['contact_urn']})",
                f"   Started at: {started_at}",
            ]
        )
    return "\n".join(lines)


def build_improvement_support_email_body(
    *,
    project_uuid: str,
    improvement_item: dict[str, Any],
    affected_conversations: list[dict[str, Any]],
    user_email: str,
) -> str:
    return "\n".join(
        [
            f"Project UUID: {project_uuid}",
            "",
            "Improvement item",
            f"- UUID: {improvement_item['uuid']}",
            f"- Text: {improvement_item['text']}",
            f"- Type: {improvement_item['type']}",
            f"- Description: {improvement_item['description']}",
            f"- Suggested change: {improvement_item['suggested_change']}",
            "- Affected instructions:",
            _format_affected_instructions(improvement_item.get("affected_instructions", [])),
            "",
            f"Affected conversations ({len(affected_conversations)})",
            _format_affected_conversations(affected_conversations),
            "",
            f"Submitted by: {user_email}",
        ]
    )


def send_improvement_support_ticket(
    *,
    project_uuid: str,
    improvement_item: dict[str, Any],
    affected_conversations: list[dict[str, Any]],
    user_email: str,
) -> int:
    if not getattr(settings, "SEND_EMAILS", True):
        logger.info(
            "[improvement_support] SEND_EMAILS=false; skipping email for project=%s",
            project_uuid,
        )
        return 0

    support_email = getattr(settings, "VTEX_SUPPORT_EMAIL", "")
    if not support_email:
        raise ValueError("VTEX_SUPPORT_EMAIL is not configured")

    subject = f"Improvement Item - {project_uuid}"
    body = build_improvement_support_email_body(
        project_uuid=project_uuid,
        improvement_item=improvement_item,
        affected_conversations=affected_conversations,
        user_email=user_email,
    )

    connection = None
    if settings.DEBUG:
        connection = get_connection(backend=CONSOLE_EMAIL_BACKEND)

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[support_email],
        reply_to=[user_email],
        connection=connection,
    )
    return email.send()
