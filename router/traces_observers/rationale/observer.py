"""
RationaleObserver processes rationale text from inline traces.

This observer extracts, improves, and sends rationale messages to users.
It has been refactored to reduce cyclomatic complexity by extracting
logic into separate handler classes and context objects.
"""
import logging
import os
from typing import Callable, Dict, Optional

import boto3
from django.conf import settings

from nexus.celery import app as celery_app
from nexus.environment import env
from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver
from nexus.event_domain.observer_factories import create_rationale_observer
from nexus.usecases.inline_agents.typing import TypingUsecase
from router.clients.flows.http.send_message import SendMessageHTTPClient
from router.clients.preview.simulator.broadcast import SimulateBroadcast
from router.traces_observers.rationale.context import RationaleContext, TraceData
from router.traces_observers.rationale.handlers import (
    FirstRationaleHandler,
    RationaleMessageSender,
    RationaleTextImprover,
    RationaleValidator,
    SubsequentRationaleHandler,
)

logger = logging.getLogger(__name__)


@observer("inline_trace_observers", factory=create_rationale_observer)
class RationaleObserver(EventObserver):
    CACHE_TIMEOUT = 300  # 5 minutes in seconds

    def __init__(
        self,
        bedrock_client=None,
        model_id=None,
        typing_usecase=None,
    ):
        """
        Initialize the RationaleObserver.

        Args:
            bedrock_client: Optional Bedrock client for testing
            model_id: Optional model ID for testing
            typing_usecase: Optional TypingUsecase instance
        """
        self.bedrock_client = bedrock_client or self._get_bedrock_client()
        self.typing_usecase = typing_usecase or TypingUsecase()
        self.model_id = model_id or settings.AWS_RATIONALE_MODEL
        self.flows_user_email = os.environ.get("FLOW_USER_EMAIL")

        # Initialize helper components to reduce complexity
        self._message_sender = RationaleMessageSender(self.typing_usecase, self.flows_user_email)
        self._text_improver = RationaleTextImprover(self.bedrock_client, self.model_id)
        self._validator = RationaleValidator()

    def _get_bedrock_client(self):
        region_name = env.str("AWS_BEDROCK_REGION_NAME")
        return boto3.client("bedrock-runtime", region_name=region_name)

    def _get_redis_task_manager(self):
        from router.tasks.redis_task_manager import RedisTaskManager

        return RedisTaskManager()

    def _handle_preview_message(
        self, text: str, urns: list, project_uuid: str, user: str, user_email: str, full_chunks: list[Dict] = None
    ) -> None:
        from nexus.projects.websockets.consumers import send_preview_message_to_websocket
        from nexus.usecases.intelligences.retrieve import get_file_info

        if not full_chunks:
            full_chunks = []

        broadcast = SimulateBroadcast(
            os.environ.get("FLOWS_REST_ENDPOINT"), os.environ.get("FLOWS_INTERNAL_TOKEN"), get_file_info
        )

        preview_response = broadcast.send_direct_message(
            text=text, urns=urns, project_uuid=project_uuid, user=user, full_chunks=full_chunks
        )

        send_preview_message_to_websocket(
            project_uuid=str(project_uuid),
            user_email=user_email,
            message_data={"type": "preview", "content": preview_response},
        )

    def perform(
        self,
        inline_traces: Dict,
        session_id: str,
        user_input: str = "",
        contact_urn: str = "",
        project_uuid: str = "",
        contact_name: str = "",
        channel_uuid: str = None,
        send_message_callback: Optional[Callable] = None,
        preview: bool = False,
        rationale_switch: bool = False,
        message_external_id: str = "",
        user_email: str = None,
        turn_off_rationale: bool = False,
        **kwargs,
    ) -> None:
        """Process rationale from inline traces."""
        if not rationale_switch or turn_off_rationale:
            return

        try:
            # Create context and trace data objects
            context = RationaleContext.from_kwargs(
                session_id=session_id,
                user_input=user_input,
                contact_urn=contact_urn,
                project_uuid=project_uuid,
                contact_name=contact_name,
                channel_uuid=channel_uuid,
                send_message_callback=send_message_callback,
                preview=preview,
                message_external_id=message_external_id,
                user_email=user_email,
            )

            trace_data = TraceData(inline_traces)
            if not trace_data.is_valid():
                return

            # Setup dependencies
            self.redis_task_manager = self._get_redis_task_manager()
            context.send_message_callback = self._setup_message_callback_if_needed(
                context.send_message_callback,
                context.message_external_id,
                context.contact_urn,
                context.project_uuid,
                context.preview,
                context.user_email,
            )

            # Process rationale
            session_data = self.redis_task_manager.get_rationale_session_data(context.session_id)
            self._process_rationale(trace_data, context, session_data)

        except Exception as e:
            logger.error(f"Error processing rationale: {str(e)}", exc_info=True)

    def _process_rationale(self, trace_data: TraceData, context: RationaleContext, session_data: Dict) -> None:
        """Process rationale text based on session state."""
        rationale_text = trace_data.get_rationale_text()
        if not rationale_text:
            return

        # Send initial typing indicator
        self._message_sender.send_typing_if_needed(
            context.message_external_id, context.contact_urn, context.project_uuid, context.preview
        )

        # Handle rationale based on session state
        if not session_data.get("is_first_rationale", True):
            self._handle_subsequent_rationale(rationale_text, context, session_data)
        else:
            self._store_first_rationale(rationale_text, context, session_data)

        # Handle first rationale with agent if conditions are met
        if self._should_handle_first_rationale_with_agent(trace_data, session_data):
            self._handle_first_rationale_with_agent(context, session_data)

    def _handle_subsequent_rationale(
        self, rationale_text: str, context: RationaleContext, session_data: Dict
    ) -> None:
        """Handle subsequent rationale processing."""
        handler = SubsequentRationaleHandler(
            self._message_sender, self._text_improver, self._validator, self.redis_task_manager
        )
        handler.handle(rationale_text, context, session_data)

    def _store_first_rationale(self, rationale_text: str, context: RationaleContext, session_data: Dict) -> None:
        """Store first rationale text for later processing."""
        session_data["first_rationale_text"] = rationale_text
        self.redis_task_manager.save_rationale_session_data(context.session_id, session_data)

    def _should_handle_first_rationale_with_agent(self, trace_data: TraceData, session_data: Dict) -> bool:
        """Check if first rationale with agent should be handled."""
        return (
            session_data.get("first_rationale_text")
            and trace_data.has_called_agent()
            and session_data.get("is_first_rationale", True)
        )

    def _handle_first_rationale_with_agent(self, context: RationaleContext, session_data: Dict) -> None:
        """Handle first rationale when agent is called."""
        handler = FirstRationaleHandler(
            self._message_sender, self._text_improver, self._validator, self.redis_task_manager
        )
        rationale_text = session_data["first_rationale_text"]
        handler.handle(rationale_text, context, session_data)

    def _setup_message_callback_if_needed(
        self, send_message_callback, message_external_id, contact_urn, project_uuid, preview, user_email
    ):
        if send_message_callback is None:
            if message_external_id:
                self.typing_usecase.send_typing_message(
                    contact_urn=contact_urn,
                    msg_external_id=message_external_id,
                    project_uuid=project_uuid,
                    preview=preview,
                )

            def send_message(text, urns, project_uuid, user, full_chunks=None):
                return self.task_send_rationale_message.delay(
                    text=text,
                    urns=urns,
                    project_uuid=project_uuid,
                    user=user,
                    full_chunks=full_chunks,
                    preview=preview,
                    user_email=user_email,
                )

            return send_message
        return send_message_callback

    @staticmethod
    @celery_app.task
    def task_send_rationale_message(
        text: str,
        urns: list,
        project_uuid: str,
        user: str,
        full_chunks: list[Dict] = None,
        preview: bool = False,
        user_email: str = None,
    ) -> None:
        if preview and user_email:
            observer = RationaleObserver()
            observer._handle_preview_message(
                text=text,
                urns=urns,
                project_uuid=project_uuid,
                user=user,
                user_email=user_email,
                full_chunks=full_chunks,
            )

        broadcast = SendMessageHTTPClient(
            os.environ.get("FLOWS_REST_ENDPOINT"), os.environ.get("FLOWS_SEND_MESSAGE_INTERNAL_TOKEN")
        )

        broadcast.send_direct_message(
            text=text, urns=urns, project_uuid=project_uuid, user=user, full_chunks=full_chunks
        )
