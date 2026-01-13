"""
Workflow observers for handling asynchronous side effects.

These observers handle non-blocking operations like:
- Sending typing indicators
- Future: Sending preview updates
- Future: Logging workflow events

Uses async observers to avoid blocking the workflow execution.
"""

import logging
from typing import Any, Optional, Type

from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver

logger = logging.getLogger(__name__)


def create_typing_indicator_observer(observer_class: Type[EventObserver]) -> EventObserver:
    """
    Factory for creating TypingIndicatorObserver with dependencies.

    This factory creates the TypingUsecase and injects it into the observer,
    making it easier to test and mock.

    Args:
        observer_class: The TypingIndicatorObserver class

    Returns:
        TypingIndicatorObserver instance with typing_usecase injected
    """
    # Lazy import to avoid circular dependencies
    from nexus.usecases.inline_agents.typing import TypingUsecase

    typing_usecase = TypingUsecase()

    return observer_class(typing_usecase=typing_usecase)


@observer(
    "workflow:send_typing_indicator",
    isolate_errors=True,
    manager="async",
    factory=create_typing_indicator_observer,
)
class TypingIndicatorObserver(EventObserver):
    """
    Sends typing indicator asynchronously when workflow starts.

    This observer is fire-and-forget - failures are logged but don't
    affect the workflow execution.

    The observer uses dependency injection for the TypingUsecase,
    making it easy to mock in tests:

        from router.tests.mocks import MockTypingUsecase

        mock_usecase = MockTypingUsecase()
        observer = TypingIndicatorObserver(typing_usecase=mock_usecase)
        await observer.perform(project_uuid="test", contact_urn="urn:test")
        mock_usecase.assert_called_once()
    """

    def __init__(self, typing_usecase: Optional[Any] = None):
        """
        Initialize with optional typing usecase.

        Args:
            typing_usecase: The usecase for sending typing messages.
                           If None, will be created lazily (for backwards compat).
        """
        self.typing_usecase = typing_usecase

    def _get_typing_usecase(self):
        """Get or create the typing usecase (lazy initialization)."""
        if self.typing_usecase is None:
            from nexus.usecases.inline_agents.typing import TypingUsecase

            self.typing_usecase = TypingUsecase()
        return self.typing_usecase

    async def perform(self, **kwargs):
        """Send typing indicator to the user."""
        contact_urn = kwargs.get("contact_urn")
        msg_external_id = kwargs.get("msg_external_id")
        project_uuid = kwargs.get("project_uuid")
        preview = kwargs.get("preview", False)

        logger.info(f"[TypingIndicatorObserver] Starting for project {project_uuid}")

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
            usecase = self._get_typing_usecase()

            # TypingUsecase is synchronous, but we're in an async observer
            # The call is quick (HTTP request with timeout), so we run it directly
            usecase.send_typing_message(
                contact_urn=contact_urn,
                msg_external_id=msg_external_id or "",
                project_uuid=project_uuid,
                preview=False,  # Already checked above
            )

            logger.info(f"[TypingIndicatorObserver] Completed for {project_uuid}")
        except Exception as e:
            # Errors are isolated - don't affect workflow
            logger.error(
                f"[TypingIndicatorObserver] Failed to send typing indicator: {e}",
                extra={"project_uuid": project_uuid, "contact_urn": contact_urn},
                exc_info=True,
            )
