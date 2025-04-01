from inline_agents.adapter import TeamAdapter
from inline_agents.team import Team


class BedrockTeamAdapter(TeamAdapter):
    @classmethod
    def to_external(self, team: Team) -> dict:
        external_team = {
            "actionGroups": self._get_action_groups(team),
            "instruction": self._get_instruction(team),
            "foundationModel": team.foundation_model,
            "sessionId": team.session_id,
            "agentCollaboration": team.agent_collaboration,
            "inputText": team.input_text,
            "inlineSessionState": team.inline_session_state,
            "knowledgeBases": self._get_knowledge_bases(team),
            "promptOverrideConfiguration": team.prompt_override_configuration,
            "enableTrace": team.enable_trace,
            "collaborators": self._get_collaborators(team),
            "collaboratorConfigurations": self._get_collaborator_configurations(team),
        }

        return external_team

    def _get_action_groups(self, team: Team) -> list:
        pass

    def _get_instruction(self, team: Team) -> str:
        pass

    def _get_foundation_model(self, team: Team) -> str:
        pass

    def _get_session_id(self, team: Team) -> str:
        pass

    def _get_agent_collaboration(self, team: Team) -> str:
        pass
