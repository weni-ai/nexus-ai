import json
import pendulum

from inline_agents.adapter import TeamAdapter

from django.conf import settings


class BedrockTeamAdapter(TeamAdapter):
    @classmethod
    def to_external(
        self,
        supervisor: dict,
        agents: list[dict],
        input_text: str,
        contact_urn: str,
        project_uuid: str
    ) -> dict:

        external_team = {
            "promptOverrideConfiguration": supervisor["promptOverrideConfiguration"],
            "instruction": supervisor["instruction"],
            "actionGroups": supervisor["actionGroups"],
            "foundationModel": supervisor["foundationModel"],
            "agentCollaboration": supervisor["agentCollaboration"],
            "knowledgeBases": supervisor["knowledgeBases"],
            "inlineSessionState": self._get_inline_session_state(),
            "enableTrace": self._get_enable_trace(),
            "sessionId": self._get_session_id(contact_urn, project_uuid),
            "inputText": input_text,
            "collaborators": self._get_collaborators(agents),
            "collaboratorConfigurations": self._get_collaborator_configurations(agents),
        }

        return external_team

    @classmethod
    def _get_session_id(cls, contact_urn: str, project_uuid: str) -> str:
        sanitized = ""
        for char in contact_urn:
            if not char.isalnum() and char not in '-_.:':
                sanitized += f"_{ord(char)}"
            else:
                sanitized += char

        return f"project-{project_uuid}-session-{sanitized}"

    @classmethod
    def _get_inline_session_state(
        cls,
        client_id: str = settings.BEDROCK_AGENT_INLINE_CLIENT_ID,
        client_secret: str = settings.BEDROCK_AGENT_INLINE_CLIENT_SECRET
    ) -> str:

        sessionState = {
            "promptSessionAttributes": {
                "date_time_now": pendulum.now("America/Sao_Paulo").add(years=3).isoformat(),
            }
        }
        sessionState["sessionAttributes"] = {
            'credentials': json.dumps({
                'CLIENT_ID': client_id,
                'CLIENT_SECRET': client_secret
            })
        }
        return sessionState

    @classmethod
    def _get_enable_trace(cls) -> str:
        return True

    @classmethod
    def _get_collaborators(cls, agents: list[dict]) -> list:
        collaborators = []
        for agent in agents:
            collaborators.append(
                {
                    "agentName": agent["agentName"],
                    "instruction": agent["instruction"],
                    "actionGroups": agent["actionGroups"],
                    "foundationModel": agent["foundationModel"],
                    "agentCollaboration": agent["agentCollaboration"],
                    # "idleSessionTTLInSeconds": agent.idle_session_ttl_in_seconds,
                }
            )
        return collaborators

    @classmethod
    def _get_collaborator_configurations(cls, agents: list[dict]) -> list[dict]:
        collaboratorConfigurations = []
        for agent in agents:
            collaboratorConfigurations += agent["collaborator_configurations"]
        return collaboratorConfigurations
