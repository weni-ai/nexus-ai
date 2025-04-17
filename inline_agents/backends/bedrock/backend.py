import boto3

from inline_agents.backend import InlineAgentsBackend
from nexus.environment import env

from .adapter import BedrockTeamAdapter
from nexus.inline_agents.backends.bedrock.repository import BedrockSupervisorRepository


class BedrockBackend(InlineAgentsBackend):
    supervisor_repository = BedrockSupervisorRepository
    team_adapter = BedrockTeamAdapter

    REGION_NAME = env.str('AWS_BEDROCK_REGION_NAME')

    def _get_client(self):
        return boto3.client('bedrock-agent-runtime', region_name=self.REGION_NAME)

    def invoke_agents(self, team: dict, input_text: str, contact_urn: str, project_uuid: str):
        supervisor = self.supervisor_repository.get_supervisor(project_uuid=project_uuid)
        # Team repository
        external_team = self.team_adapter.to_external(
            supervisor=supervisor,
            agents=team,
            input_text=input_text,
            contact_urn=contact_urn,
            project_uuid=project_uuid
        )
        client = self._get_client()

        response = client.invoke_inline_agent(**external_team)

        # TODO: Invoke inline agent
        # TODO: Implement observer to traces

        return response
