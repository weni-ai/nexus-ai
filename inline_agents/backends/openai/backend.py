import asyncio
from typing import Any, Dict

import pendulum
from agents import Agent, Runner, trace
from django.conf import settings
from langfuse import get_client
from redis import Redis

from inline_agents.backend import InlineAgentsBackend
from inline_agents.backends.openai.adapter import (
    OpenAIDataLakeEventAdapter,
    OpenAITeamAdapter,
)
from inline_agents.backends.openai.entities import FinalResponse
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
from nexus.projects.websockets.consumers import (
    send_preview_message_to_websocket,
)
from nexus.usecases.jwt.jwt_usecase import JWTUsecase
from router.traces_observers.save_traces import save_inline_message_to_database


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

    def _get_session(self, project_uuid: str, sanitized_urn: str, conversation_turns_to_include: int | None = None) -> tuple[RedisSession, str]:
        redis_client = Redis.from_url(settings.REDIS_URL)
        session_id = f"project-{project_uuid}-session-{sanitized_urn}"
        return RedisSession(session_id=session_id, r=redis_client, project_uuid=project_uuid, sanitized_urn=sanitized_urn, limit=conversation_turns_to_include), session_id

    def _get_session_factory(self, project_uuid: str, sanitized_urn: str, conversation_turns_to_include: int | None = None):
        redis_client = Redis.from_url(settings.REDIS_URL)
        session_id = f"project-{project_uuid}-session-{sanitized_urn}"
        return make_session_factory(redis=redis_client, base_id=session_id, project_uuid=project_uuid, sanitized_urn=sanitized_urn, limit=conversation_turns_to_include)

    def end_session(self, project_uuid: str, sanitized_urn: str):
        session, session_id = self._get_session(project_uuid=project_uuid, sanitized_urn=sanitized_urn)
        session.clear_session()

    def _get_event_manager_notify(self):
        if self._event_manager_notify is None:
            from nexus.events import async_event_manager
            self._event_manager_notify = async_event_manager.notify
        return self._event_manager_notify

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
        **kwargs
    ):
        turns_to_include = None
        self._event_manager_notify = event_manager_notify or self._get_event_manager_notify()
        session_factory = self._get_session_factory(
            project_uuid=project_uuid,
            sanitized_urn=sanitized_urn,
            conversation_turns_to_include=turns_to_include
        )
        session, session_id = self._get_session(
            project_uuid=project_uuid,
            sanitized_urn=sanitized_urn,
            conversation_turns_to_include=turns_to_include
        )

        supervisor: Dict[str, Any] = self.supervisor_repository.get_supervisor(project=project)
        data_lake_event_adapter = self._get_data_lake_event_adapter()

        hooks_state = HooksState(agents=team)

        save_inline_message_to_database(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            text=input_text,
            preview=preview,
            session_id=session_id,
            source_type="user",
            contact_name=contact_name,
            channel_uuid=channel_uuid
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
                    "session_id": session_id
                }
            )

        result = asyncio.run(self._invoke_agents_async(
            client, external_team, session, session_id,
            input_text, contact_urn, project_uuid, channel_uuid,
            user_email, preview, rationale_switch, language,
            turn_off_rationale, msg_external_id, supervisor_hooks, runner_hooks, hooks_state
        ))
        return result

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
    ):
        """Async wrapper to handle the streaming response"""
        with self.langfuse_c.start_as_current_span(name="OpenAI Agents trace: Agent workflow") as root_span:
            trace_id = f"trace_urn:{contact_urn}_{pendulum.now().strftime('%Y%m%d_%H%M%S')}".replace(":", "__")[:64]
            print(f"[+ DEBUG +] Trace ID: {trace_id}")
            with trace(workflow_name=project_uuid, trace_id=trace_id):
                result = client.run_streamed(**external_team, session=session, hooks=runner_hooks)
                async for event in result.stream_events():
                    if event.type == "run_item_stream_event":
                        if hasattr(event, 'item') and event.item.type == "tool_call_item":
                            hooks_state.tool_calls.update({
                                event.item.raw_item.name: event.item.raw_item.arguments   
                            })
                final_response = self._get_final_response(result)
                root_span.update_trace(
                    input=input_text,
                    output=final_response,
                    metadata={
                        "project_uuid": project_uuid,
                        "contact_urn": contact_urn,
                        "channel_uuid": channel_uuid,
                        "preview": preview,
                    }
                )
        return self._get_final_response(result)

    def _get_final_response(self, result):
        if isinstance(result.final_output, FinalResponse):
            return result.final_output.final_response
        else:
            return result.final_output
