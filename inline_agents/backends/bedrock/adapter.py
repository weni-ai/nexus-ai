import json
import pendulum
from django.conf import settings
import os

from inline_agents.adapter import TeamAdapter
from inline_agents.backends.bedrock.prompts import PROMPT_POS_PROCESSING

from django.utils.text import slugify
from nexus.inline_agents.components import Components
from nexus.inline_agents.models import AgentCredential, Guardrail


class BedrockTeamAdapter(TeamAdapter):
    @classmethod
    def to_external(
        self,
        supervisor: dict,
        agents: list[dict],
        input_text: str,
        contact_urn: str,
        project_uuid: str,
        use_components: bool = False,
        contact_fields: str = ""
    ) -> dict:
        # TODO: change self to cls
        from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
        from nexus.projects.models import Project
        content_base = get_default_content_base_by_project(project_uuid)
        instructions = content_base.instructions.all()
        agent_data = content_base.agent

        project = Project.objects.get(uuid=project_uuid)
        business_rules = project.human_support_prompt
        supervisor_instructions = list(instructions.values_list("instruction", flat=True))
        supervisor_instructions = "\n".join(supervisor_instructions)

        time_now = pendulum.now("America/Sao_Paulo")
        llm_formatted_time = f"Today is {time_now.format('dddd, MMMM D, YYYY [at] HH:mm:ss z')}"

        instruction = self._format_supervisor_instructions(
            instruction=supervisor["instruction"],
            date_time_now=llm_formatted_time,
            contact_fields=contact_fields,
            supervisor_name=agent_data.name,
            supervisor_role=agent_data.role,
            supervisor_goal=agent_data.goal,
            supervisor_adjective=agent_data.personality,
            supervisor_instructions=supervisor_instructions if supervisor_instructions else "",
            business_rules=business_rules if business_rules else "",
            project_id=project_uuid,
            contact_id=contact_urn
        )

        credentials = self._get_credentials(project_uuid)

        external_team = {
            "instruction": instruction,
            "actionGroups": supervisor["action_groups"],
            "foundationModel": supervisor["foundation_model"],
            "agentCollaboration": supervisor["agent_collaboration"],
            "knowledgeBases": self._get_knowledge_bases(
                supervisor=supervisor,
                content_base_uuid=content_base.uuid
            ),
            "inlineSessionState": self._get_inline_session_state(
                use_components=use_components,
                credentials=credentials,
                contact={"urn": contact_urn},
                project={"uuid": project_uuid}
            ),
            "enableTrace": self._get_enable_trace(),
            "sessionId": self._get_session_id(contact_urn, project_uuid),
            "inputText": input_text,
            "collaborators": self._get_collaborators(agents, llm_formatted_time),
            "collaboratorConfigurations": self._get_collaborator_configurations(agents),
            "guardrailConfiguration": self._get_guardrails(),
            "promptOverrideConfiguration": self.__get_prompt_override_configuration(use_components=use_components)
        }

        print(f"[ + DEBUG + ] external_team: {external_team}")

        return external_team

    @classmethod
    def _get_credentials(cls, project_uuid: str) -> dict:
        agent_credentials = AgentCredential.objects.filter(project_id=project_uuid)
        credentials = {}
        for credential in agent_credentials:
            credentials[credential.key] = credential.decrypted_value
        return credentials

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
        use_components: bool,
        credentials: dict,
        contact: dict,
        project: dict
    ) -> str:
        sessionState = {}
        session_attributes = {}

        if credentials:
            session_attributes['credentials'] = json.dumps(credentials, default=str)

        if contact:
            session_attributes["contact"] = json.dumps(contact, default=str)
        
        if project:
            session_attributes["project"] = json.dumps(project, default=str)

        sessionState["sessionAttributes"] = session_attributes

        return sessionState

    @classmethod
    def _get_enable_trace(cls) -> str:
        return True

    @classmethod
    def _get_collaborators(cls, agents: list[dict], date_time_now: str) -> list:
        collaborators = []
        for agent in agents:

            instruction = agent["instruction"]
            if settings.COLLABORATORS_DEFAULT_INSTRUCTIONS:
                instruction = instruction + "\n\n" + settings.COLLABORATORS_DEFAULT_INSTRUCTIONS
                instruction = instruction.replace("{{DATE_TIME_NOW}}", date_time_now)

            collaborators.append(
                {
                    "agentName": agent["agentName"],
                    "instruction": instruction,
                    "actionGroups": agent["actionGroups"],
                    "foundationModel": agent["foundationModel"],
                    "agentCollaboration": agent["agentCollaboration"],
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

    @classmethod
    def _get_knowledge_bases(
        cls,
        supervisor: dict,
        content_base_uuid: str
    ) -> list[dict]:

        single_filter = {
            "equals": {
                "key": "contentBaseUuid",
                "value": str(content_base_uuid)
            }
        }

        retrieval_configuration = {
            "vectorSearchConfiguration": {
                "filter": single_filter
            }
        }

        knowledge = supervisor["knowledge_bases"][0]

        knowledge.update(
            {"retrievalConfiguration": retrieval_configuration}
        )

        return [knowledge]

    @classmethod
    def _format_supervisor_instructions(
        cls,
        instruction: str,
        date_time_now: str,
        contact_fields: str,
        supervisor_name: str,
        supervisor_role: str,
        supervisor_goal: str,
        supervisor_adjective: str,
        supervisor_instructions: str,
        business_rules: str,
        project_id: str,
        contact_id: str
    ) -> str:

        instruction = instruction or ""
        date_time_now = date_time_now or ""
        contact_fields = contact_fields or ""
        supervisor_name = supervisor_name or ""
        supervisor_role = supervisor_role or ""
        supervisor_goal = supervisor_goal or ""
        supervisor_adjective = supervisor_adjective or ""
        supervisor_instructions = supervisor_instructions or ""
        business_rules = business_rules or ""
        project_id = str(project_id) if project_id else ""
        contact_id = str(contact_id) if contact_id else ""

        instruction = instruction.replace(
            "{{DATE_TIME_NOW}}", date_time_now
        ).replace(
            "{{CONTACT_FIELDS}}", contact_fields
        ).replace(
            "{{SUPERVISOR_NAME}}", supervisor_name
        ).replace(
            "{{SUPERVISOR_ROLE}}", supervisor_role
        ).replace(
            "{{SUPERVISOR_GOAL}}", supervisor_goal
        ).replace(
            "{{SUPERVISOR_ADJECTIVE}}", supervisor_adjective
        ).replace(
            "{{SUPERVISOR_INSTRUCTIONS}}", supervisor_instructions
        ).replace(
            "{{BUSINESS_RULES}}", business_rules
        ).replace(
            "{{PROJECT_ID}}", project_id
        ).replace(
            "{{CONTACT_ID}}", contact_id
        )
        return instruction

    @classmethod
    def _get_guardrails(cls) -> list[dict]:
        guardrails = Guardrail.objects.filter(current_version=True).order_by("created_on").last()
        return {
            'guardrailIdentifier': guardrails.identifier,
            'guardrailVersion': str(guardrails.version)
        }

    @classmethod
    def __get_prompt_override_configuration(self, use_components: bool) -> dict:
        prompt_override_configuration = {
            'promptConfigurations': [
                {
                    'promptType': 'KNOWLEDGE_BASE_RESPONSE_GENERATION',
                    'promptState': 'DISABLED',
                    'promptCreationMode': 'DEFAULT',
                    'parserMode': 'DEFAULT'
                },
                {
                    'promptType': 'PRE_PROCESSING',
                    'promptState': 'DISABLED',
                    'promptCreationMode': 'DEFAULT',
                    'parserMode': 'DEFAULT'
                },
                {
                    'promptType': 'POST_PROCESSING',
                    'promptState': 'DISABLED',
                    'promptCreationMode': 'DEFAULT',
                    'parserMode': 'DEFAULT'
                }
            ]
        }

        if use_components:
            prompt_override_configuration.update(
                {'overrideLambda': os.environ.get('AWS_COMPONENTS_FUNCTION_ARN')}
            )
            prompt_override_configuration["promptConfigurations"].append(
                {
                    'basePromptTemplate': PROMPT_POS_PROCESSING,
                    'foundationModel': settings.AWS_BEDROCK_AGENTS_MODEL_ID[0],
                    'inferenceConfiguration': {
                        'maximumLength': 2048,
                        'stopSequences': [
                            'Human:',
                        ],
                        'temperature': 0, 
                        'topK': 250,
                        'topP': 1
                    },
                    
                    'promptType': 'POST_PROCESSING',
                    'promptState': 'ENABLED',
                    'parserMode': 'OVERRIDDEN',
                    'promptCreationMode': 'OVERRIDDEN'
                }
            )
        return prompt_override_configuration

    @classmethod
    def __get_collaborator_prompt_override_configuration(self) -> dict:
        return {
            'promptConfigurations': [
                {
                    'promptType': 'KNOWLEDGE_BASE_RESPONSE_GENERATION',
                    'promptState': 'DISABLED',
                    'promptCreationMode': 'DEFAULT',
                    'parserMode': 'DEFAULT'
                },
                {
                    'promptType': 'PRE_PROCESSING',
                    'promptState': 'DISABLED',
                    'promptCreationMode': 'DEFAULT',
                    'parserMode': 'DEFAULT'
                },
                {
                    'promptType': 'POST_PROCESSING',
                    'promptState': 'DISABLED',
                    'promptCreationMode': 'DEFAULT',
                    'parserMode': 'DEFAULT'
                }
            ]
        }
