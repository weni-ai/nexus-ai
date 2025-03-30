from inline_agents.adapter import TeamAdapter
from inline_agents.team import Team


class BedrockTeamAdapter(TeamAdapter):
    @classmethod
    def to_external(self, team: Team) -> dict:
        pass
