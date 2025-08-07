import asyncio
from typing import Any, Dict

from agents import Agent, Runner
from django.conf import settings
from redis import Redis

from inline_agents.backend import InlineAgentsBackend
from inline_agents.backends.openai.adapter import OpenAITeamAdapter
from inline_agents.backends.openai.sessions import RedisSession
from nexus.inline_agents.backends.openai.models import (
    OpenAISupervisor as Supervisor,
)
from inline_agents.backends.openai.hooks import HooksDefault
from nexus.projects.websockets.consumers import (
    send_preview_message_to_websocket,
)


class OpenAISupervisorRepository:
    @classmethod
    def get_supervisor(
        cls,
        project_uuid: str
    ) -> Agent:
        from nexus.projects.models import Project

        project = Project.objects.get(uuid=project_uuid)
        supervisor = Supervisor.objects.order_by('id').last()

        if not supervisor:
            raise Supervisor.DoesNotExist()

        supervisor_dict = {
            "instruction": cls._get_supervisor_instructions(project=project, supervisor=supervisor),
            "tools": supervisor.action_groups,
            "foundation_model": supervisor.foundation_model,
            "knowledge_bases": supervisor.knowledge_bases,
        }

        return supervisor_dict
    
    @classmethod
    def _get_supervisor_instructions(cls, project, supervisor) -> str:
        if project.use_components and project.human_support:
            return supervisor.components_human_support_prompt
        elif project.use_components:
            return supervisor.components_prompt
        elif project.human_support:
            return supervisor.human_support_prompt
        else:
            return supervisor.instruction


class OpenAIBackend(InlineAgentsBackend):
    supervisor_repository = OpenAISupervisorRepository
    team_adapter = OpenAITeamAdapter

    def _get_client(self):
        return Runner()

    def _get_session(self, project_uuid: str, sanitized_urn: str) -> tuple[RedisSession, str]:
        redis_client = Redis.from_url(settings.REDIS_URL)
        session_id = f"project-{project_uuid}-session-{sanitized_urn}"
        return RedisSession(session_id=session_id, r=redis_client), session_id

    def invoke_agents(self,
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
        **kwargs
    ):
        hooks = HooksDefault()
        supervisor: Dict[str, Any] = self.supervisor_repository.get_supervisor(project_uuid)
        external_team = self.team_adapter.to_external(
            supervisor=supervisor,
            agents=team,
            input_text=input_text,
            project_uuid=project_uuid,
            contact_fields=contact_fields,
            contact_urn=sanitized_urn,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
            hooks=hooks
        )
        client = self._get_client()
        session, session_id = self._get_session(project_uuid=project_uuid, sanitized_urn=sanitized_urn)

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

        result = asyncio.run(self._invoke_agents_async(client, external_team, session))
        print("========================= Tools called ========================")
        print(hooks.list_tools_called)
        print("========================================================")
        return result

    async def _invoke_agents_async(self, client, external_team, session):
        """Async wrapper to handle the streaming response"""
        full_response = ""
        result = client.run_streamed(**external_team, session=session)
        
        async for event in result.stream_events():
            if event.type == "raw_response_event":
                if hasattr(event.data, 'delta'):
                    full_response += event.data.delta
            elif event.type == "run_item_stream_event":
                pass
        return result.final_output
