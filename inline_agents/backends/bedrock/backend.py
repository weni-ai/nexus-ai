import boto3

from inline_agents.backend import InlineAgentsBackend
from nexus.environment import env

from .adapter import BedrockTeamAdapter
from nexus.inline_agents.backends.bedrock.repository import BedrockSupervisorRepository
from nexus.events import event_manager


class BedrockBackend(InlineAgentsBackend):
    supervisor_repository = BedrockSupervisorRepository
    team_adapter = BedrockTeamAdapter

    REGION_NAME = env.str('AWS_BEDROCK_REGION_NAME')

    def __init__(self, event_manager_notify=event_manager.notify):
        self.event_manager_notify = event_manager_notify

    def _get_client(self):
        return boto3.client('bedrock-agent-runtime', region_name=self.REGION_NAME)

    def invoke_agents(
        self,
        team: dict,
        input_text: str,
        contact_urn: str,
        project_uuid: str,
        preview: bool = False
    ):
        supervisor = self.supervisor_repository.get_supervisor(project_uuid=project_uuid)

        external_team = self.team_adapter.to_external(
            supervisor=supervisor,
            agents=team,
            input_text=input_text,
            contact_urn=contact_urn,
            project_uuid=project_uuid
        )
        print("--------------------------------")
        print(f"[DEBUG] External team: {external_team}")
        print("--------------------------------")
        client = self._get_client()

        response = client.invoke_inline_agent(**external_team)

        completion = response["completion"]
        full_response = ""
        for event in completion:
            if 'chunk' in event:
                full_response += event['chunk']['bytes'].decode()
            if 'trace' in event:
                self.event_manager_notify(
                    event="inline_trace_observers",
                    inline_traces=event['trace'],
                    user_input=input_text,
                    contact_urn=contact_urn,
                    project_uuid=project_uuid,
                    send_message_callback=None,
                    preview=preview
                )
            print("--------------------------------")
            print(f"[DEBUG] Event: {event}")
            print("--------------------------------")

        return full_response
