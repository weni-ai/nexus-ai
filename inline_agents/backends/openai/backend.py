# ruff: noqa: E501
import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import openai
import pendulum
import sentry_sdk
from django.conf import settings
from langfuse import get_client
from openai.types.shared import Reasoning
from redis import Redis

from inline_agents.backend import InlineAgentsBackend
from inline_agents.backends.openai.adapter import OpenAIDataLakeEventAdapter, OpenAITeamAdapter
from inline_agents.backends.openai.components_tools import get_component_tools as get_component_tools_module
from inline_agents.backends.openai.entities import FinalResponse
from inline_agents.backends.openai.grpc import (
    MessageStreamingClient,
    is_grpc_enabled,
)
from inline_agents.backends.openai.hooks import (
    HooksState,
    RunnerHooks,
    SupervisorHooks,
)
from inline_agents.backends.openai.sessions import (
    RedisSession,
    make_session_factory,
)
from nexus.inline_agents.backends.openai.repository import (
    OpenAISupervisorRepository,
)
from nexus.inline_agents.models import InlineAgentsConfiguration
from nexus.intelligences.models import ContentBase
from nexus.projects.models import Project
from nexus.projects.websockets.consumers import send_preview_message_to_websocket
from nexus.usecases.jwt.jwt_usecase import JWTUsecase
from router.traces_observers.save_traces import save_inline_message_to_database

logger = logging.getLogger(__name__)


class OpenAIBackend(InlineAgentsBackend):
    supervisor_repository = OpenAISupervisorRepository
    team_adapter = OpenAITeamAdapter

    def __init__(self):
        super().__init__()
        self._event_manager_notify = None
        self._data_lake_event_adapter = None
        self.langfuse_c = get_client()

    def _get_data_lake_event_adapter(self):
        if self._data_lake_event_adapter is None:
            self._data_lake_event_adapter = OpenAIDataLakeEventAdapter()
        return self._data_lake_event_adapter

    def _get_client(self):
        from agents import Runner

        return Runner()

    def _get_session(
        self, project_uuid: str, sanitized_urn: str, conversation_turns_to_include: int | None = None
    ) -> tuple[RedisSession, str]:
        redis_client = Redis.from_url(settings.REDIS_URL)
        session_id = f"project-{project_uuid}-session-{sanitized_urn}"
        return RedisSession(
            session_id=session_id,
            r=redis_client,
            project_uuid=project_uuid,
            sanitized_urn=sanitized_urn,
            limit=conversation_turns_to_include,
        ), session_id

    def _get_session_factory(
        self, project_uuid: str, sanitized_urn: str, conversation_turns_to_include: int | None = None
    ):
        redis_client = Redis.from_url(settings.REDIS_URL)
        session_id = f"project-{project_uuid}-session-{sanitized_urn}"
        return make_session_factory(
            redis=redis_client,
            base_id=session_id,
            project_uuid=project_uuid,
            sanitized_urn=sanitized_urn,
            limit=conversation_turns_to_include,
        )

    def end_session(self, project_uuid: str, sanitized_urn: str):
        session, session_id = self._get_session(project_uuid=project_uuid, sanitized_urn=sanitized_urn)
        session.clear_session()

    def _get_event_manager_notify(self):
        if self._event_manager_notify is None:
            from nexus.events import async_event_manager

            self._event_manager_notify = async_event_manager.notify
        return self._event_manager_notify

    def _ensure_conversation(
        self, project_uuid: str, contact_urn: str, contact_name: str, channel_uuid: str, preview: bool = False
    ) -> Optional[object]:
        """Ensure conversation exists and return it, or None if creation fails or channel_uuid is missing."""
        # Don't create conversations in preview mode
        if preview:
            return None

        if not channel_uuid:
            # channel_uuid is None - log to Sentry for debugging
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_tag("contact_urn", contact_urn)
            sentry_sdk.set_context(
                "conversation_creation",
                {
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "contact_name": contact_name,
                    "channel_uuid": None,
                    "backend": "openai",
                    "reason": "channel_uuid is None",
                },
            )
            sentry_sdk.capture_message(
                "Conversation not created: channel_uuid is None (OpenAI backend)", level="warning"
            )
            return None

        try:
            from router.services.conversation_service import ConversationService

            conversation_service = ConversationService()
            return conversation_service.ensure_conversation_exists(
                project_uuid=project_uuid, contact_urn=contact_urn, contact_name=contact_name, channel_uuid=channel_uuid
            )
        except Exception as e:
            # If conversation lookup/creation fails, continue without it but log to Sentry
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_tag("contact_urn", contact_urn)
            sentry_sdk.set_tag("channel_uuid", channel_uuid)
            sentry_sdk.set_context(
                "conversation_creation",
                {
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "contact_name": contact_name,
                    "channel_uuid": channel_uuid,
                    "backend": "openai",
                },
            )
            sentry_sdk.capture_exception(e)
            return None

    def invoke_agents(
        self,
        team: list[dict],
        input_text: str,
        project_uuid: str,
        sanitized_urn: str,
        contact_fields: str,
        project: Project,
        content_base: ContentBase,
        preview: bool = False,
        language: str = "en",
        contact_name: str = "",
        contact_urn: str = "",
        channel_uuid: str = "",
        use_components: bool = False,
        user_email: str = None,
        rationale_switch: bool = False,
        msg_external_id: str = None,
        turn_off_rationale: bool = False,
        event_manager_notify: callable = None,
        inline_agent_configuration: InlineAgentsConfiguration | None = None,
        **kwargs,
    ):
        turns_to_include = None
        self._event_manager_notify = event_manager_notify or self._get_event_manager_notify()
        session_factory = self._get_session_factory(
            project_uuid=project_uuid, sanitized_urn=sanitized_urn, conversation_turns_to_include=turns_to_include
        )
        session, session_id = self._get_session(
            project_uuid=project_uuid, sanitized_urn=sanitized_urn, conversation_turns_to_include=turns_to_include
        )

        supervisor: Dict[str, Any] = self.supervisor_repository.get_supervisor(project=project)
        data_lake_event_adapter = self._get_data_lake_event_adapter()

        # Ensure conversation exists and get it for data lake events (skip in preview mode)
        conversation = self._ensure_conversation(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
            preview=preview,
        )

        hooks_state = HooksState(agents=team)

        save_inline_message_to_database(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            text=input_text,
            preview=preview,
            session_id=session_id,
            source_type="user",
            contact_name=contact_name,
            channel_uuid=channel_uuid,
        )

        supervisor_hooks = SupervisorHooks(
            agent_name="manager",
            preview=preview,
            rationale_switch=rationale_switch,
            language=language,
            user_email=user_email,
            session_id=session_id,
            msg_external_id=msg_external_id,
            turn_off_rationale=turn_off_rationale,
            event_manager_notify=self._event_manager_notify,
            agents=team,
            hooks_state=hooks_state,
            data_lake_event_adapter=data_lake_event_adapter,
            conversation=conversation,
            use_components=use_components,
        )
        runner_hooks = RunnerHooks(
            supervisor_name="manager",
            preview=preview,
            rationale_switch=rationale_switch,
            language=language,
            user_email=user_email,
            session_id=session_id,
            msg_external_id=msg_external_id,
            turn_off_rationale=turn_off_rationale,
            event_manager_notify=self._event_manager_notify,
            agents=team,
            hooks_state=hooks_state,
        )

        jwt_usecase = JWTUsecase()
        auth_token = jwt_usecase.generate_jwt_token(project_uuid)

        external_team = self.team_adapter.to_external(
            supervisor=supervisor,
            agents=team,
            input_text=input_text,
            project_uuid=project_uuid,
            contact_fields=contact_fields,
            contact_urn=contact_urn,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
            supervisor_hooks=supervisor_hooks,
            runner_hooks=runner_hooks,
            project=project,
            content_base=content_base,
            inline_agent_configuration=inline_agent_configuration,
            session_factory=session_factory,
            session=session,
            data_lake_event_adapter=data_lake_event_adapter,
            preview=preview,
            hooks_state=hooks_state,
            event_manager_notify=self._event_manager_notify,
            rationale_switch=rationale_switch,
            language=language,
            user_email=user_email,
            session_id=session_id,
            msg_external_id=msg_external_id,
            turn_off_rationale=turn_off_rationale,
            auth_token=auth_token,
            use_components=use_components,
        )

        client = self._get_client()

        if preview and user_email:
            send_preview_message_to_websocket(
                project_uuid=str(project_uuid),
                user_email=user_email,
                message_data={
                    "type": "status",
                    "content": "Starting OpenAI agent processing",
                    "session_id": session_id,
                },
            )

        grpc_client, grpc_msg_id = None, None
        if not preview:
            grpc_client, grpc_msg_id = self._initialize_grpc_client(
                channel_uuid=channel_uuid,
                contact_urn=contact_urn,
                session_id=session_id,
                project_uuid=project_uuid,
                language=language,
            )

        result = asyncio.run(
            self._invoke_agents_async(
                client,
                external_team,
                session,
                session_id,
                input_text,
                contact_urn,
                project_uuid,
                channel_uuid,
                user_email,
                preview,
                rationale_switch,
                language,
                turn_off_rationale,
                msg_external_id,
                supervisor_hooks,
                runner_hooks,
                hooks_state,
                use_components,
                grpc_client=grpc_client,
                grpc_msg_id=grpc_msg_id,
                formatter_agent_configurations=project.formatter_agent_configurations,
            )
        )

        if grpc_client and grpc_msg_id:
            try:
                content = result if isinstance(result, str) else str(result)
                grpc_client.send_completed_message(
                    msg_id=grpc_msg_id,
                    content=content,
                    channel_uuid=channel_uuid,
                    contact_urn=contact_urn,
                    project_uuid=str(project_uuid),
                )
            except Exception as e:
                logger.error(f"gRPC completion failed: {e}", exc_info=True)
            finally:
                grpc_client.close()

        return result

    async def _run_formatter_agent_async(
        self,
        final_response: str,
        session,
        supervisor_hooks,
        context,
        formatter_instructions="",
        formatter_agent_configurations=None,
    ):
        """Run the formatter agent asynchronously within the trace context"""
        # Create formatter agent to process the final response
        formatter_agent = self._create_formatter_agent(
            supervisor_hooks, formatter_instructions, formatter_agent_configurations
        )

        # Run the formatter agent with the final response
        formatter_result = await self._run_formatter_agent(
            formatter_agent, final_response, session, context, formatter_agent_configurations
        )

        return formatter_result

    def _create_formatter_agent(self, supervisor_hooks, formatter_instructions="", formatter_agent_configurations=None):
        """Create the formatter agent with component tools"""

        def custom_tool_handler(context, tool_results):
            if tool_results:
                first_result = tool_results[0]
                from agents.agent import ToolsToFinalOutputResult

                return ToolsToFinalOutputResult(is_final_output=True, final_output=first_result.output)
            from agents.agent import ToolsToFinalOutputResult

            return ToolsToFinalOutputResult(is_final_output=False, final_output=None)

        # Use custom instructions if provided, otherwise use default
        instructions = (
            formatter_instructions
            or "Format the final response using appropriate JSON components. Analyze all provided information (simple message, products, options, links, context) and choose the best component automatically."
        )
        logger.debug(
            "Formatter agent configurations", extra={"keys": list((formatter_agent_configurations or {}).keys())}
        )
        # Handle None case for formatter_agent_configurations
        if formatter_agent_configurations is None:
            formatter_agent_configurations = {}

        # Use value if not None, otherwise use default
        formatter_agent_model: str = (
            formatter_agent_configurations.get("formatter_foundation_model") or settings.FORMATTER_AGENT_MODEL
        )
        formatter_instructions: str = formatter_agent_configurations.get("formatter_instructions") or instructions
        formatter_reasoning_effort: str = formatter_agent_configurations.get("formatter_reasoning_effort")
        formatter_reasoning_summary: str = formatter_agent_configurations.get("formatter_reasoning_summary") or "auto"
        formatter_tools_descriptions: bool = formatter_agent_configurations.get("formatter_tools_descriptions")
        tools = get_component_tools_module(formatter_tools_descriptions)

        supervisor_hooks.save_components_trace = True

        from agents import Agent, ModelSettings

        formatter_agent = Agent(
            name="Response Formatter Agent",
            instructions=formatter_instructions,
            model=formatter_agent_model,
            tools=tools,
            hooks=supervisor_hooks,
            tool_use_behavior=custom_tool_handler,
            model_settings=ModelSettings(tool_choice="required", parallel_tool_calls=False),
        )

        if formatter_reasoning_effort:
            from agents import ModelSettings

            formatter_agent.model_settings = ModelSettings(
                reasoning=Reasoning(effort=formatter_reasoning_effort, summary=formatter_reasoning_summary)
            )

        return formatter_agent

    async def _run_formatter_agent(
        self, formatter_agent, final_response, session, context, formatter_agent_configurations
    ):
        """Run the formatter agent with the final response"""
        from agents import Runner

        try:
            formatter_send_only_assistant_message = (
                formatter_agent_configurations.get("formatter_send_only_assistant_message") or False
            )
            if formatter_send_only_assistant_message:
                input_formatter = await session.get_items()
                result = await Runner.run(
                    starting_agent=formatter_agent,
                    input=input_formatter,
                    context=context,
                )
                return result.final_output

            result = await Runner.run(
                starting_agent=formatter_agent,
                input=final_response,
                context=context,
                session=session,
            )
            # Only stream events if the result has stream_events method
            stream_events = getattr(result, "stream_events", None)
            if stream_events and callable(stream_events):
                async for _ in stream_events():
                    pass
            return self._get_final_response(result)
        except Exception as e:
            logger.error("Error in formatter agent: %s", e, exc_info=True)
            # Return the original response if formatter fails
            return final_response

    def _initialize_grpc_client(
        self, channel_uuid: str, contact_urn: str, session_id: str, project_uuid: str, language: str
    ) -> tuple[Optional[MessageStreamingClient], Optional[str]]:
        """Initialize gRPC client and send setup message."""
        if not is_grpc_enabled() or not contact_urn:
            return None, None

        if not channel_uuid:
            channel_uuid = "default-channel-uuid"

        try:
            grpc_host = getattr(settings, "GRPC_SERVICE_HOST", "localhost")
            grpc_port = getattr(settings, "GRPC_SERVICE_PORT", 50051)
            grpc_use_tls = getattr(settings, "GRPC_USE_TLS", False)

            grpc_client = MessageStreamingClient(host=grpc_host, port=grpc_port, use_secure_channel=grpc_use_tls)

            grpc_msg_id = hashlib.sha256(
                f"{contact_urn}-{session_id}-{datetime.now().isoformat()}".encode()
            ).hexdigest()[:16]

            for _ in grpc_client.stream_messages_with_setup(
                msg_id=grpc_msg_id,
                channel_uuid=channel_uuid,
                contact_urn=contact_urn,
                project_uuid=str(project_uuid),
                metadata={
                    "session_id": session_id,
                    "language": language,
                },
            ):
                pass

            return grpc_client, grpc_msg_id

        except Exception as e:
            logger.error(f"gRPC setup failed: {e}", exc_info=True)
            return None, None

    def _send_grpc_delta(
        self,
        delta_content: str,
        grpc_client: MessageStreamingClient,
        grpc_msg_id: str,
        delta_counter: int,
        channel_uuid: str,
        contact_urn: str,
        project_uuid: str,
    ):
        """Send a delta message via gRPC."""
        try:
            grpc_client.send_delta_message(
                msg_id=grpc_msg_id,
                content=delta_content,
                channel_uuid=channel_uuid,
                contact_urn=contact_urn,
                project_uuid=str(project_uuid),
            )
        except Exception as e:
            logger.error(f"gRPC delta send failed: {e}", exc_info=True)

    def _process_delta_event(
        self,
        event,
        grpc_client: Optional[MessageStreamingClient],
        grpc_msg_id: Optional[str],
        delta_counter: int,
        channel_uuid: str,
        contact_urn: str,
        project_uuid: str,
    ) -> int:
        """Process a delta event and stream it via gRPC."""
        from openai.types.responses import ResponseTextDeltaEvent

        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            delta_content = event.data.delta
            if delta_content and grpc_client and grpc_msg_id:
                delta_counter += 1
                self._send_grpc_delta(
                    delta_content=delta_content,
                    grpc_client=grpc_client,
                    grpc_msg_id=grpc_msg_id,
                    delta_counter=delta_counter,
                    channel_uuid=channel_uuid,
                    contact_urn=contact_urn,
                    project_uuid=project_uuid,
                )
        return delta_counter

    async def _invoke_agents_async(
        self,
        client,
        external_team,
        session,
        session_id,
        input_text,
        contact_urn,
        project_uuid,
        channel_uuid,
        user_email,
        preview,
        rationale_switch,
        language,
        turn_off_rationale,
        msg_external_id,
        supervisor_hooks,
        runner_hooks,
        hooks_state,
        use_components,
        grpc_client: Optional[MessageStreamingClient] = None,
        grpc_msg_id: Optional[str] = None,
        formatter_agent_configurations=None,
    ):
        """Async wrapper to handle the streaming response"""
        from agents import trace

        with self.langfuse_c.start_as_current_span(name="OpenAI Agents trace: Agent workflow") as root_span:
            trace_id = f"trace_urn:{contact_urn}_{pendulum.now().strftime('%Y%m%d_%H%M%S')}".replace(":", "__")[:64]
            with trace(workflow_name=project_uuid, trace_id=trace_id):
                formatter_agent_instructions = external_team.pop("formatter_agent_instructions", "")
                result = client.run_streamed(
                    **external_team, session=session, hooks=runner_hooks, max_turns=settings.OPENAI_AGENTS_MAX_TURNS
                )
            delta_counter = 0
            try:
                # Only stream events if the result has stream_events method
                stream_events = getattr(result, "stream_events", None)
                if stream_events and callable(stream_events):
                    async for event in stream_events():
                        delta_counter = self._process_delta_event(
                            event=event,
                            grpc_client=grpc_client,
                            grpc_msg_id=grpc_msg_id,
                            delta_counter=delta_counter,
                            channel_uuid=channel_uuid,
                            contact_urn=contact_urn,
                            project_uuid=project_uuid,
                        )
                        if hasattr(event, "item") and event.type == "run_item_stream_event":
                            if event.item.type == "tool_call_item":
                                hooks_state.tool_calls.update({event.item.raw_item.name: event.item.raw_item.arguments})
            except openai.APIError as api_error:
                self._sentry_capture_exception(
                    api_error, project_uuid, contact_urn, channel_uuid, session_id, input_text, enable_logger=True
                )
                raise
            except Exception as stream_error:
                self._sentry_capture_exception(
                    stream_error,
                    project_uuid,
                    contact_urn,
                    channel_uuid,
                    session_id,
                    input_text,
                    enable_logger=True,
                )
                # Try to get final_response even if streaming failed
                try:
                    final_response = self._get_final_response(result)
                except Exception:
                    final_response = None

                root_span.update_trace(
                    input=input_text,
                    output=final_response,
                    metadata={
                        "project_uuid": project_uuid,
                        "contact_urn": contact_urn,
                        "channel_uuid": channel_uuid,
                        "preview": preview,
                        "trace_id": trace_id,
                        "error": True,
                        "error_type": type(stream_error).__name__,
                        "error_message": str(stream_error)[:500],
                    },
                )

                if use_components and final_response:
                    try:
                        formatted_response = await self._run_formatter_agent_async(
                            final_response,
                            session,
                            supervisor_hooks,
                            external_team["context"],
                            formatter_agent_instructions,
                            formatter_agent_configurations,
                        )
                        final_response = formatted_response
                    except Exception as formatter_error:
                        logger.error(
                            f"[OpenAIBackend] Error in formatter agent after streaming error: {formatter_error}",
                            extra={
                                "project_uuid": project_uuid,
                                "contact_urn": contact_urn,
                            },
                        )

                return final_response

            final_response = self._get_final_response(result)

            if use_components:
                formatted_response = await self._run_formatter_agent_async(
                    final_response,
                    session,
                    supervisor_hooks,
                    external_team["context"],
                    formatter_agent_instructions,
                    formatter_agent_configurations,
                )
                final_response = formatted_response

            root_span.update_trace(
                input=input_text,
                output=final_response,
                metadata={
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "channel_uuid": channel_uuid,
                    "preview": preview,
                    "trace_id": trace_id,
                },
            )

        return final_response

    def _get_final_response(self, result):
        if isinstance(result.final_output, FinalResponse):
            final_response = result.final_output.final_response
        else:
            final_response = result.final_output
        return final_response

    def _sentry_capture_exception(
        self, exception, project_uuid, contact_urn, channel_uuid, session_id, input_text, enable_logger
    ):
        if enable_logger:
            logger.error(
                f"[OpenAIBackend] Streaming error during agent execution: {exception}",
                extra={
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "channel_uuid": channel_uuid,
                    "session_id": session_id,
                    "error_type": type(exception).__name__,
                    "error_message": str(exception),
                    "input_text": input_text[:500] if input_text else None,
                },
            )

        sentry_sdk.set_context(
            "streaming_error",
            {
                "project_uuid": project_uuid,
                "contact_urn": contact_urn,
                "channel_uuid": channel_uuid,
                "session_id": session_id,
                "error_type": type(exception).__name__,
                "error_message": str(exception),
                "input_text_preview": input_text[:200] if input_text else None,
            },
        )
        sentry_sdk.set_tag("project_uuid", project_uuid)
        sentry_sdk.set_tag("error_type", "streaming_error")
        sentry_sdk.capture_exception(exception)
