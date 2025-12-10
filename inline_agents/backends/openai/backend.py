# ruff: noqa: E501
import asyncio
import logging
from typing import Any, Dict, Optional

import pendulum
import sentry_sdk
from agents import Agent, ModelSettings, Runner, trace
from agents.agent import ToolsToFinalOutputResult
from django.conf import settings
from langfuse import get_client
from openai.types.shared import Reasoning
from redis import Redis

from inline_agents.backend import InlineAgentsBackend
from inline_agents.backends.openai.adapter import OpenAIDataLakeEventAdapter, OpenAITeamAdapter
from inline_agents.backends.openai.components_tools import COMPONENT_TOOLS
from inline_agents.backends.openai.entities import FinalResponse
from inline_agents.backends.openai.hooks import HooksState, RunnerHooks, SupervisorHooks
from inline_agents.backends.openai.sessions import RedisSession, make_session_factory
from nexus.inline_agents.backends.openai.repository import OpenAISupervisorRepository
from nexus.inline_agents.models import InlineAgentsConfiguration
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
        self,
        project_uuid: str,
        contact_urn: str,
        contact_name: str,
        channel_uuid: str,
        preview: bool = False
    ) -> Optional[object]:
        """Ensure conversation exists and return it, or None if creation fails or channel_uuid is missing."""
        # Don't create conversations in preview mode
        if preview:
            return None

        if not channel_uuid:
            # channel_uuid is None - log to Sentry for debugging
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_tag("contact_urn", contact_urn)
            sentry_sdk.set_context("conversation_creation", {
                "project_uuid": project_uuid,
                "contact_urn": contact_urn,
                "contact_name": contact_name,
                "channel_uuid": None,
                "backend": "openai",
                "reason": "channel_uuid is None"
            })
            sentry_sdk.capture_message(
                "Conversation not created: channel_uuid is None (OpenAI backend)",
                level="warning"
            )
            return None

        try:
            from router.services.conversation_service import ConversationService

            conversation_service = ConversationService()
            return conversation_service.ensure_conversation_exists(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                contact_name=contact_name,
                channel_uuid=channel_uuid
            )
        except Exception as e:
            # If conversation lookup/creation fails, continue without it but log to Sentry
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_tag("contact_urn", contact_urn)
            sentry_sdk.set_tag("channel_uuid", channel_uuid)
            sentry_sdk.set_context("conversation_creation", {
                "project_uuid": project_uuid,
                "contact_urn": contact_urn,
                "contact_name": contact_name,
                "channel_uuid": channel_uuid,
                "backend": "openai"
            })
            sentry_sdk.capture_exception(e)
            return None

    def invoke_agents(
        self,
        team: list[dict],
        input_text: str,
        project_uuid: str,
        sanitized_urn: str,
        contact_fields: str,
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

        use_components_cached = kwargs.pop("use_components", use_components)
        rationale_switch_cached = kwargs.pop("rationale_switch", rationale_switch)
        conversation_turns_to_include_cached = kwargs.pop("conversation_turns_to_include", None)
        human_support_cached = kwargs.pop("human_support", None)
        default_supervisor_foundation_model_cached = kwargs.pop("default_supervisor_foundation_model", None)
        formatter_agent_configurations = kwargs.pop("formatter_agent_configurations", None)
        rationale_switch = rationale_switch_cached
        turns_to_include = conversation_turns_to_include_cached

        self._event_manager_notify = event_manager_notify or self._get_event_manager_notify()
        session_factory = self._get_session_factory(
            project_uuid=project_uuid, sanitized_urn=sanitized_urn, conversation_turns_to_include=turns_to_include
        )
        session, session_id = self._get_session(
            project_uuid=project_uuid, sanitized_urn=sanitized_urn, conversation_turns_to_include=turns_to_include
        )

        # Cached data is always provided from start_inline_agents
        supervisor: Dict[str, Any] = self.supervisor_repository.get_supervisor(
            use_components=use_components_cached,
            human_support=human_support_cached,
            default_supervisor_foundation_model=default_supervisor_foundation_model_cached,
        )
        data_lake_event_adapter = self._get_data_lake_event_adapter()

        # Ensure conversation exists and get it for data lake events (skip in preview mode)
        conversation = self._ensure_conversation(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
            preview=preview
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

        # Extract cached data if available from kwargs
        content_base_uuid_cached = kwargs.pop("content_base_uuid", None)
        business_rules_cached = kwargs.pop("business_rules", None)
        instructions_cached = kwargs.pop("instructions", None)
        agent_data_cached = kwargs.pop("agent_data", None)
        default_instructions_for_collaborators_cached = kwargs.pop("default_instructions_for_collaborators", None)

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
            inline_agent_configuration=inline_agent_configuration,
            session_factory=session_factory,
            session=session,
            data_lake_event_adapter=data_lake_event_adapter,
            preview=preview,
            hooks_state=hooks_state,
            event_manager_notify=self._event_manager_notify,
            # Pass cached data to avoid database queries
            content_base_uuid=content_base_uuid_cached,
            business_rules=business_rules_cached,
            instructions=instructions_cached,
            agent_data=agent_data_cached,
            default_instructions_for_collaborators=default_instructions_for_collaborators_cached,
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
                formatter_agent_configurations=formatter_agent_configurations,
            )
        )
        return result

    async def _run_formatter_agent_async(
        self, final_response: str, session, supervisor_hooks, context, formatter_instructions="", formatter_agent_configurations=None
    ):
        """Run the formatter agent asynchronously within the trace context"""
        # Create formatter agent to process the final response
        formatter_agent = self._create_formatter_agent(supervisor_hooks, formatter_instructions, formatter_agent_configurations)

        # Run the formatter agent with the final response
        formatter_result = await self._run_formatter_agent(formatter_agent, final_response, session, context, formatter_agent_configurations)

        return formatter_result

    def _create_formatter_agent(self, supervisor_hooks, formatter_instructions="", formatter_agent_configurations=None):
        """Create the formatter agent with component tools"""

        def custom_tool_handler(context, tool_results):
            if tool_results:
                first_result = tool_results[0]
                return ToolsToFinalOutputResult(is_final_output=True, final_output=first_result.output)
            return ToolsToFinalOutputResult(is_final_output=False, final_output=None)

        def get_component_tools(formatter_tools_descriptions: dict):
            if not formatter_tools_descriptions:
                return COMPONENT_TOOLS
            for index, tool in enumerate(COMPONENT_TOOLS):
                tool_name = tool.name
                tool_description = formatter_tools_descriptions.get(tool_name)
                print(f"tool: {tool_name}, tem descrição: {tool_description != None}")
                if tool_description:
                    COMPONENT_TOOLS[index].description = tool_description
            return COMPONENT_TOOLS

        # Use custom instructions if provided, otherwise use default
        instructions = (
            formatter_instructions
            or "Format the final response using appropriate JSON components. Analyze all provided information (simple message, products, options, links, context) and choose the best component automatically."
        )
        print(formatter_agent_configurations)
        # Handle None case for formatter_agent_configurations
        if formatter_agent_configurations is None:
            formatter_agent_configurations = {}

        # Use value if not None, otherwise use default
        formatter_agent_model: str = formatter_agent_configurations.get("formatter_foundation_model") or settings.FORMATTER_AGENT_MODEL
        formatter_instructions: str = formatter_agent_configurations.get("formatter_instructions") or instructions
        formatter_reasoning_effort: str = formatter_agent_configurations.get("formatter_reasoning_effort")
        formatter_reasoning_summary: str = formatter_agent_configurations.get("formatter_reasoning_summary") or "auto"
        formatter_tools_descriptions: bool = formatter_agent_configurations.get("formatter_tools_descriptions")
        tools = get_component_tools(formatter_tools_descriptions)

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
            formatter_agent.model_settings = ModelSettings(reasoning=Reasoning(effort=formatter_reasoning_effort, summary=formatter_reasoning_summary))

        return formatter_agent

    async def _run_formatter_agent(self, formatter_agent, final_response, session, context, formatter_agent_configurations):
        """Run the formatter agent with the final response"""
        try:
            formatter_send_only_assistant_message = formatter_agent_configurations.get("formatter_send_only_assistant_message") or False
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
            return result.final_output
        except Exception as e:
            print(f"Error in formatter agent: {e}")
            return final_response

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
        formatter_agent_configurations=None,
    ):
        """Async wrapper to handle the streaming response"""
        with self.langfuse_c.start_as_current_span(name="OpenAI Agents trace: Agent workflow") as root_span:
            trace_id = f"trace_urn:{contact_urn}_{pendulum.now().strftime('%Y%m%d_%H%M%S')}".replace(":", "__")[:64]
            print(f"[+ DEBUG +] Trace ID: {trace_id}")
            with trace(workflow_name=project_uuid, trace_id=trace_id):
                # Extract formatter_agent_instructions before passing to Runner.run_streamed
                formatter_agent_instructions = external_team.pop("formatter_agent_instructions", "")
                result = client.run_streamed(**external_team, session=session, hooks=runner_hooks, max_turns=settings.OPENAI_AGENTS_MAX_TURNS)

                try:
                    async for event in result.stream_events():
                        if event.type == "run_item_stream_event":
                            if hasattr(event, "item") and event.item.type == "tool_call_item":
                                hooks_state.tool_calls.update({event.item.raw_item.name: event.item.raw_item.arguments})
                except Exception as stream_error:
                    logger.error(
                        f"[OpenAIBackend] Streaming error during agent execution: {stream_error}",
                        extra={
                            "project_uuid": project_uuid,
                            "contact_urn": contact_urn,
                            "channel_uuid": channel_uuid,
                            "session_id": session_id,
                            "error_type": type(stream_error).__name__,
                            "error_message": str(stream_error),
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
                            "error_type": type(stream_error).__name__,
                            "error_message": str(stream_error),
                            "input_text_preview": input_text[:200] if input_text else None,
                        },
                    )
                    sentry_sdk.set_tag("project_uuid", project_uuid)
                    sentry_sdk.set_tag("error_type", "streaming_error")
                    sentry_sdk.capture_exception(stream_error)

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

                # If use_components is True, process the result through the formatter agent
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
                    },
                )

        return final_response

    def _get_final_response(self, result):
        if isinstance(result.final_output, FinalResponse):
            final_response = result.final_output.final_response
        else:
            final_response = result.final_output
        return final_response
