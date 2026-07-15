"""Runtime-only progressive feedback instruction injected during orchestration."""

import logging

from django.conf import settings

from router.traces_observers.rationale.channel_hint import (
    channel_hint_from_contact_urn,
    supports_progressive_feedback,
)

logger = logging.getLogger(__name__)

DEFAULT_PROGRESSIVE_FEEDBACK_ORCHESTRATION_INSTRUCTION = (
    "Before executing ANY tool or calling an agent, send the user a short feedback message "
    "explaining what you're about to do, so they know the request is being processed."
)

CORE_IDENTITY_MARKERS = ("<core_identity>", "## Core Identity")


def get_progressive_feedback_orchestration_instruction() -> str:
    return getattr(settings, "PROGRESSIVE_FEEDBACK_ORCHESTRATION_INSTRUCTION", "") or ""


def should_inject_progressive_feedback_instruction(
    rationale_switch: bool,
    turn_off_rationale: bool,
    contact_urn: str = "",
    channel_type: str = "",
    preview: bool = False,
    preview_websocket: bool = False,
) -> bool:
    return (
        rationale_switch
        and not turn_off_rationale
        and supports_progressive_feedback(
            contact_urn,
            channel_type,
            preview=preview,
            preview_websocket=preview_websocket,
        )
    )


def find_core_identity_marker(prompt: str) -> str | None:
    for marker in CORE_IDENTITY_MARKERS:
        if marker in prompt:
            return marker
    return None


def inject_progressive_feedback_instruction(rendered_prompt: str, instruction: str) -> str:
    instruction = instruction.strip()
    if not instruction:
        return rendered_prompt

    for marker in CORE_IDENTITY_MARKERS:
        idx = rendered_prompt.find(marker)
        if idx != -1:
            prefix = rendered_prompt[:idx].rstrip()
            suffix = rendered_prompt[idx:]
            if prefix:
                return f"{prefix}\n\n{instruction}\n\n{suffix}"
            return f"{instruction}\n\n{suffix}"

    return f"{instruction}\n\n{rendered_prompt}"


def log_progressive_feedback_orchestration_decision(
    *,
    project_id: str,
    rationale_switch: bool,
    turn_off_rationale: bool,
    injected: bool,
    contact_urn: str = "",
    channel_type: str = "",
    preview: bool = False,
    preview_websocket: bool = False,
    instruction_preview: str | None = None,
) -> None:
    channel_from_urn = channel_hint_from_contact_urn(contact_urn) if contact_urn else None
    if injected:
        logger.info(
            "[ProgressiveFeedback] Orchestration instruction injected project_id=%s channel_from_urn=%s "
            "contact_urn=%s instruction_preview=%r",
            project_id,
            channel_from_urn,
            contact_urn or None,
            instruction_preview,
        )
        return

    if not rationale_switch or turn_off_rationale:
        logger.info(
            "[ProgressiveFeedback] Orchestration instruction skipped project_id=%s channel_from_urn=%s "
            "contact_urn=%s rationale_switch=%s turn_off_rationale=%s",
            project_id,
            channel_from_urn,
            contact_urn or None,
            rationale_switch,
            turn_off_rationale,
        )
        return

    if not supports_progressive_feedback(
        contact_urn,
        channel_type,
        preview=preview,
        preview_websocket=preview_websocket,
    ):
        logger.info(
            "[ProgressiveFeedback] Orchestration instruction skipped project_id=%s channel_from_urn=%s "
            "contact_urn=%s channel_type=%s reason=non_webchat",
            project_id,
            channel_from_urn,
            contact_urn or None,
            channel_type or None,
        )
        return

    logger.info(
        "[ProgressiveFeedback] Orchestration instruction skipped project_id=%s channel_from_urn=%s "
        "contact_urn=%s reason=empty_instruction",
        project_id,
        channel_from_urn,
        contact_urn or None,
    )
