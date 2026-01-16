import asyncio
import logging
from typing import Any, Dict, Optional

from inline_agents.backends.openai.backend import OpenAIBackend
from inline_agents.backends.openai.entities import HooksState
from inline_agents.backends.openai.hooks import RunnerHooks, SupervisorHooks
from inline_agents.backends.openai.redis_pool import get_redis_client
from inline_agents.backends.openai.sessions import RedisSession, make_session_factory
from inline_agents.backends.openai.workflow_adapter import WorkflowTeamAdapter
from nexus.inline_agents.models import InlineAgentsConfiguration
from nexus.projects.websockets.consumers import send_preview_message_to_websocket

logger = logging.getLogger(__name__)


class OpenAIWorkflowBackend(OpenAIBackend):
    # Use WorkflowTeamAdapter instead of OpenAITeamAdapter
    team_adapter = WorkflowTeamAdapter

    @property
    def name(self) -> str:
        return "OpenAIWorkflowBackend"

    def _get_session_with_id(
        self, project_uuid: str, sanitized_urn: str, session_id: str, conversation_turns_to_include: int | None = None
    ):
        # Use connection pool instead of creating new connection each time
        redis_client = get_redis_client()
        return RedisSession(
            session_id=session_id,
            r=redis_client,
            project_uuid=project_uuid,
            sanitized_urn=sanitized_urn,
            limit=conversation_turns_to_include,
        )

    def _get_session_factory(
        self, project_uuid: str, sanitized_urn: str, conversation_turns_to_include: int | None = None
    ):
        # Override to use connection pool
        redis_client = get_redis_client()
        session_id = f"project-{project_uuid}-session-{sanitized_urn}"
        return make_session_factory(
            redis=redis_client,
            base_id=session_id,
            project_uuid=project_uuid,
            sanitized_urn=sanitized_urn,
            limit=conversation_turns_to_include,
        )

    def _get_conversation_by_id(self, conversation_id: str) -> Optional[object]:
        if not conversation_id:
            return None

        from nexus.intelligences.models import Conversation

        try:
            return Conversation.objects.get(uuid=conversation_id)
        except Conversation.DoesNotExist:
            logger.warning(f"[OpenAIWorkflowBackend] Conversation {conversation_id} not found")
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
        channel_type: str = "",
        use_components: bool = False,
        user_email: str = None,
        rationale_switch: bool = False,
        msg_external_id: str = None,
        turn_off_rationale: bool = False,
        event_manager_notify: callable = None,
        inline_agent_configuration: InlineAgentsConfiguration | None = None,
        **kwargs,
    ):
        # Extract pre-fetched data - REQUIRED for workflow execution
        pre_fetched_session_id = kwargs.pop("_pre_fetched_session_id")
        pre_fetched_auth_token = kwargs.pop("_pre_fetched_auth_token")
        pre_fetched_credentials = kwargs.pop("_pre_fetched_credentials")
        pre_fetched_conversation_id = kwargs.pop("_pre_fetched_conversation_id", None)

        logger.debug("[OpenAIWorkflowBackend] Using pre-fetched data from pre-generation")

        use_components_cached = kwargs.pop("use_components", use_components)
        rationale_switch_cached = kwargs.pop("rationale_switch", rationale_switch)
        human_support_cached = kwargs.pop("human_support", None)
        default_supervisor_foundation_model_cached = kwargs.pop("default_supervisor_foundation_model", None)
        formatter_agent_configurations = kwargs.pop("formatter_agent_configurations", None)
        rationale_switch = rationale_switch_cached

        turns_to_include = None

        self._event_manager_notify = event_manager_notify or self._get_event_manager_notify()

        session_id = pre_fetched_session_id
        session_factory = self._get_session_factory(
            project_uuid=project_uuid, sanitized_urn=sanitized_urn, conversation_turns_to_include=turns_to_include
        )
        session = self._get_session_with_id(
            project_uuid=project_uuid,
            sanitized_urn=sanitized_urn,
            session_id=session_id,
            conversation_turns_to_include=turns_to_include,
        )

        supervisor: Dict[str, Any] = self.supervisor_repository.get_supervisor(
            use_components=use_components_cached,
            human_support=human_support_cached,
            default_supervisor_foundation_model=default_supervisor_foundation_model_cached,
        )
        data_lake_event_adapter = self._get_data_lake_event_adapter()

        if pre_fetched_conversation_id:
            conversation = self._get_conversation_by_id(pre_fetched_conversation_id)
        else:
            conversation = None

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

        auth_token = pre_fetched_auth_token

        content_base_uuid_cached = kwargs.pop("content_base_uuid", None)
        business_rules_cached = kwargs.pop("business_rules", None)
        instructions_cached = kwargs.pop("instructions", None)
        agent_data_cached = kwargs.pop("agent_data", None)
        default_instructions_for_collaborators_cached = kwargs.pop("default_instructions_for_collaborators", None)

        # Pass pre-fetched credentials to WorkflowTeamAdapter (avoids DB query)
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
            credentials=pre_fetched_credentials,  # Pass pre-fetched credentials
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
        if not preview and not use_components:
            grpc_client, grpc_msg_id = self._initialize_grpc_client(
                channel_uuid=channel_uuid,
                contact_urn=contact_urn,
                session_id=session_id,
                project_uuid=project_uuid,
                language=language,
                channel_type=channel_type,
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
                formatter_agent_configurations=formatter_agent_configurations,
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
