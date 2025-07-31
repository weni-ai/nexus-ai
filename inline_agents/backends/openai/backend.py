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

    def _get_session(self, project_uuid: str, sanitized_urn: str):
        redis_client = Redis.from_url(settings.REDIS_URL)
        return RedisSession(session_id=f"project-{project_uuid}-session-{sanitized_urn}", r=redis_client)

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
        )
        client = self._get_client()
        session = self._get_session(project_uuid=project_uuid, sanitized_urn=sanitized_urn)
        print("=========================EXTERNAL TEAM========================")
        print(external_team)
        print("=========================EXTERNAL TEAM========================")

        return asyncio.run(self._invoke_agents_async(client, external_team, session))

    async def _invoke_agents_async(self, client, external_team, session):
        """Async wrapper to handle the streaming response"""
        full_response = ""
        result = client.run_streamed(**external_team, session=session)
        
        async for event in result.stream_events():
            if event.type == "raw_response_event":
                if hasattr(event.data, 'delta'):
                    full_response += event.data.delta
            elif event.type == "run_item_stream_event":
                if event.item.type == "message_output_item":
                    from agents import ItemHelpers
                    message_text = ItemHelpers.text_message_output(event.item)
                    if message_text:
                        full_response += message_text
        print("=========================FULL RESPONSE========================")
        print(full_response)
        print("=========================FULL RESPONSE========================")
        return full_response
