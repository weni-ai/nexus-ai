"""
Workflow observers for handling asynchronous side effects.

These observers handle non-blocking operations like:
- Sending typing indicators
- Future: Sending preview updates
- Future: Logging workflow events

Uses async observers to avoid blocking the workflow execution.
"""

import logging

from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver

logger = logging.getLogger(__name__)


@observer("workflow:send_typing_indicator", isolate_errors=True, manager="async")
class TypingIndicatorObserver(EventObserver):
    """
    Sends typing indicator asynchronously when workflow starts.

    This observer is fire-and-forget - failures are logged but don't
    affect the workflow execution.
    """

    async def perform(self, **kwargs):
        """Send typing indicator to the user."""
        contact_urn = kwargs.get("contact_urn")
        msg_external_id = kwargs.get("msg_external_id")
        project_uuid = kwargs.get("project_uuid")
        preview = kwargs.get("preview", False)

        if not contact_urn or not project_uuid:
            logger.warning(
                "[TypingIndicatorObserver] Missing required parameters",
                extra={"contact_urn": contact_urn, "project_uuid": project_uuid},
            )
            return

        if preview:
            logger.debug("[TypingIndicatorObserver] Skipping typing indicator for preview mode")
            return

        try:
            # Lazy import to avoid circular dependencies
            from nexus.usecases.inline_agents.typing import TypingUsecase

            # TypingUsecase is synchronous, but we're in an async observer
            # The call is quick (HTTP request with timeout), so we run it directly
            TypingUsecase().send_typing_message(
                contact_urn=contact_urn,
                msg_external_id=msg_external_id or "",
                project_uuid=project_uuid,
                preview=False,  # Already checked above
            )

            logger.debug(
                f"[TypingIndicatorObserver] Typing indicator sent for {project_uuid}",
                extra={"project_uuid": project_uuid, "contact_urn": contact_urn},
            )
        except Exception as e:
            # Errors are isolated - don't affect workflow
            logger.error(
                f"[TypingIndicatorObserver] Failed to send typing indicator: {e}",
                extra={"project_uuid": project_uuid, "contact_urn": contact_urn},
                exc_info=True,
            )
