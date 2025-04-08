import json
import pendulum

from inline_agents.adapter import TeamAdapter

from django.utils.text import slugify



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
            # "promptOverrideConfiguration": supervisor["prompt_override_configuration"],
            "instruction": supervisor["instruction"],
            "actionGroups": supervisor["action_groups"],
            "foundationModel": supervisor["foundation_model"],
            "agentCollaboration": supervisor["agent_collaboration"],
            "knowledgeBases": supervisor["knowledge_bases"],
            "inlineSessionState": self._get_inline_session_state(
                contact_urn=contact_urn,
                # contact_fields_as_json=contact_fields_as_json,
                project_uuid=project_uuid,
            ),
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
        contact_urn: str,
        # contact_fields_as_json: str,
        project_uuid: str,
    ) -> str:
        from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project

        content_base = get_default_content_base_by_project(project_uuid)
        instructions = content_base.instructions.all()
        agent_data = content_base.agent

        sessionState = {
            "promptSessionAttributes": {
                "date_time_now": pendulum.now("America/Sao_Paulo").isoformat(),
            }
        }
        sessionState["promptSessionAttributes"] = {
            # "format_components": get_all_formats(),
            "contact_urn": contact_urn,
            # "contact_fields": contact_fields_as_json,
            "date_time_now": pendulum.now("America/Sao_Paulo").isoformat(),
            "project_id": project_uuid,
            "specific_personality": json.dumps({
                "occupation": agent_data.role,
                "name": agent_data.name,
                "goal": agent_data.goal,
                "adjective": agent_data.personality,
                "instructions": list(instructions.values_list("instruction", flat=True))
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
            collaboratorConfigurations.append(
                {
                    "collaboratorInstruction": agent["collaborator_configurations"],
                    "collaboratorName": slugify(agent["agentName"])
                }
            )
        return collaboratorConfigurations
