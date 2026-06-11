"""Runtime-only progressive feedback instruction injected during orchestration."""

from django.conf import settings

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
) -> bool:
    return rationale_switch and not turn_off_rationale


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
