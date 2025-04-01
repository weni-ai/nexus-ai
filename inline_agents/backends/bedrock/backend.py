import boto3

from inline_agents.backend import InlineAgentsBackend
from inline_agents.team import Team
from nexus.environment import env

from .adapter import BedrockTeamAdapter


class BedrockBackend(InlineAgentsBackend):

    team_adapter = BedrockTeamAdapter

    REGION_NAME = env.str('AWS_BEDROCK_REGION_NAME')

    def _get_client(self):
        return boto3.client('bedrock-agent-runtime', region_name=self.REGION_NAME)

    def invoke_agents(self, team: Team):
        external_team = self.team_adapter.to_external(team)
        client = self._get_client()

        response = client.invoke_inline_agent(**external_team)

        # TODO: Invoke inline agent
        # TODO: Implement observer to traces
