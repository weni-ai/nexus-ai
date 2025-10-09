import asyncio
from typing import Any, Dict

from agents import Runner
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
from nexus.usecases.jwt.jwt_usecase import JWTUsecase
from router.traces_observers.save_traces import save_inline_message_to_database


class OpenAICallingBackend(InlineAgentsBackend):
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
        return (
            RedisSession(
                session_id=session_id,
                r=redis_client,
                project_uuid=project_uuid,
                sanitized_urn=sanitized_urn,
                limit=conversation_turns_to_include,
            ),
            session_id,
        )

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

        hooks_state = HooksState(agents=team)

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

        # jwt_usecase = JWTUsecase()
        # auth_token = jwt_usecase.generate_jwt_token(project_uuid)
        auth_token = ""

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

        result = asyncio.run(self._invoke_agents_async(external_team))
        return result

    def _remove_tools_stricts(self, tools):
        cleaned_tools = []

        for tool in tools:
            new_tool = {k: v for k, v in tool.items() if k != "strict"}
            cleaned_tools.append(new_tool)

        return cleaned_tools

    async def _invoke_agents_async(self, external_team):
        from agents.models.openai_responses import Converter
        from agents.run import AgentRunner, RunConfig
        from agents.run_context import RunContextWrapper, TContext
        from agents.util import _coro
        from agents.util._json import _to_dump_compatible

        context = external_team.get("context")
        current_agent = external_team.get("starting_agent")

        context_wrapper: RunContextWrapper[TContext] = RunContextWrapper(context=context)

        all_tools = await AgentRunner._get_all_tools(current_agent, context_wrapper)
        handoffs = await AgentRunner._get_handoffs(current_agent, context_wrapper)

        converted_tools = Converter.convert_tools(all_tools, handoffs)
        converted_tools_payload = _to_dump_compatible(converted_tools.tools)

        run_config = RunConfig()

        system_prompt, _ = await asyncio.gather(
            current_agent.get_system_prompt(context_wrapper),
            current_agent.get_prompt(context_wrapper),
        )

        filtered = await AgentRunner._maybe_filter_model_input(
            agent=current_agent,
            run_config=run_config,
            context_wrapper=context_wrapper,
            input_items=input,
            system_instructions=system_prompt,
        )

        converted_tools_payload = self._remove_tools_stricts(converted_tools_payload)

        return {"instructions": filtered.instructions, "tools": converted_tools_payload}

    def _get_final_response(self, result):
        if isinstance(result.final_output, FinalResponse):
            return result.final_output.final_response
        else:
            return result.final_output
