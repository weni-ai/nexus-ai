from inline_agents.backend import InlineAgentsBackend
from inline_agents.adapter import TeamAdapter
from inline_agents.team import Team

from nexus.environment import env


class OpenAIBackend(InlineAgentsBackend):
    def invoke_agents(self, team: Team, team_adapter: TeamAdapter):
        external_team = team_adapter.to_external(team)

        # TODO: Invoke inline agent
        # TODO: Implement observer to traces
