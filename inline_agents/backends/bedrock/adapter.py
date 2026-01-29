import json
import logging
from typing import Optional

import pendulum
import sentry_sdk
from django.conf import settings
from django.utils.text import slugify
from weni_datalake_sdk.clients.client import send_event_data
from weni_datalake_sdk.paths.events_path import EventPath

from inline_agents.adapter import DataLakeEventAdapter, TeamAdapter
from inline_agents.backends.bedrock.event_extractor import BedrockEventExtractor
from inline_agents.data_lake.event_service import DataLakeEventService
from nexus.celery import app as celery_app
from nexus.inline_agents.models import Agent, AgentCredential, Guardrail, IntegratedAgent
from nexus.utils import get_datasource_id

logger = logging.getLogger(__name__)


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
        contact_fields: str = "",
        contact_name: str = "",
        channel_uuid: str = "",
        auth_token: str = "",
        sanitized_urn: str = "",
        classification_foundation_model: str = None,
        project=None,
        content_base=None,
        **kwargs,
    ) -> dict:
        # TODO: change self to cls
        from nexus.projects.models import Project
        from nexus.usecases.intelligences.get_by_uuid import (
            get_default_content_base_by_project,
        )

        if content_base is None:
            content_base = get_default_content_base_by_project(project_uuid)
        instructions = content_base.instructions.all()
        agent_data = content_base.agent

        if project is None:
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
            contact_id=contact_urn,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
        )

        logger.debug(f"Auth token present - token_len: {len(auth_token or '')}")

        credentials = self._get_credentials(project_uuid, agents)

        if classification_foundation_model:
            foundation_model = classification_foundation_model
        else:
            foundation_model = supervisor["foundation_model"]

        external_team = {
            "instruction": instruction,
            "actionGroups": supervisor["action_groups"],
            "foundationModel": foundation_model,
            "agentCollaboration": supervisor["agent_collaboration"],
            "knowledgeBases": self._get_knowledge_bases(
                supervisor=supervisor,
                content_base_uuid=content_base.uuid,
                project_uuid=project_uuid,
            ),
            "inlineSessionState": self._get_inline_session_state(
                use_components=use_components,
                credentials=credentials,
                contact={"urn": contact_urn, "name": contact_name, "channel_uuid": channel_uuid},
                project={"uuid": project_uuid, "auth_token": auth_token},
            ),
            "enableTrace": self._get_enable_trace(),
            "sessionId": self._get_session_id(sanitized_urn, project_uuid),
            "inputText": input_text,
            "collaborators": self._get_collaborators(agents, llm_formatted_time),
            "collaboratorConfigurations": self._get_collaborator_configurations(agents),
            "guardrailConfiguration": self._get_guardrails(project_uuid=project_uuid),
            "promptOverrideConfiguration": self.__get_prompt_override_configuration(
                use_components=use_components,
                prompt_override_configuration=supervisor["prompt_override_configuration"],
            ),
            "idleSessionTTLInSeconds": settings.AWS_BEDROCK_IDLE_SESSION_TTL_IN_SECONDS,
        }

        logger.debug(f"External team built - agents_count: {len(external_team.get('agents', []))}")

        return external_team

    @classmethod
    def _get_credentials(cls, project_uuid: str, agents: list[dict] = None) -> dict:
        agent_credentials = AgentCredential.objects.filter(project_id=project_uuid)
        credentials = {}
        for credential in agent_credentials:
            credentials[credential.key] = credential.decrypted_value

        if not agents:
            return credentials

        merged_credentials = credentials.copy()

        for agent_dict in agents:
            agent_name = agent_dict.get("agentName")
            if not agent_name:
                continue

            agent = (
                Agent.objects.filter(slug=agent_name, project__uuid=project_uuid)
                .prefetch_related("mcps__credential_templates")
                .first()
            )
            if not agent:
                continue

            integrated_agent = IntegratedAgent.objects.filter(agent=agent, project__uuid=project_uuid).first()

            if not integrated_agent or not integrated_agent.metadata:
                continue

            mcp_name = integrated_agent.metadata.get("mcp")
            if not mcp_name:
                continue

            mcp = agent.mcps.filter(name=mcp_name, is_active=True).prefetch_related("credential_templates").first()

            if not mcp:
                continue

            mcp_credentials = {}
            credential_templates = mcp.credential_templates.all()
            if credential_templates:
                template_names = {template.name for template in credential_templates}
                for credential in agent_credentials:
                    if credential.key in template_names:
                        mcp_credentials[credential.key] = credential.decrypted_value

            mcp_config = integrated_agent.metadata.get("mcp_config", {})
            if isinstance(mcp_config, dict):
                merged_credentials.update(mcp_credentials)
                merged_credentials.update(mcp_config)

        return merged_credentials

    @classmethod
    def _get_session_id(cls, contact_urn: str, project_uuid: str) -> str:
        sanitized = ""
        for char in contact_urn:
            if not char.isalnum() and char not in "-_.:":
                sanitized += f"_{ord(char)}"
            else:
                sanitized += char

        session_id = f"project-{project_uuid}-session-{sanitized}"
        session_id_length = len(session_id)

        if session_id_length > 100:
            session_length = 100 - (len(session_id) - len(sanitized))

            if project_uuid in settings.PROJECTS_WITH_SPECIAL_SESSION_ID:
                session_id = f"project-{project_uuid}-session-{sanitized[-session_length:]}"
            else:
                session_id = session_id[:100]

            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.capture_message(f"Session ID is too long: {session_id} - {session_id_length}", level="warning")

        return session_id

    @classmethod
    def _get_inline_session_state(
        cls,
        use_components: bool,
        credentials: dict,
        contact: dict,
        project: dict,
    ) -> str:
        sessionState = {}
        session_attributes = {}

        if credentials:
            session_attributes["credentials"] = json.dumps(credentials, default=str)

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
                    "collaboratorName": slugify(agent["agentName"]),
                }
            )
        return collaboratorConfigurations

    @classmethod
    def _get_knowledge_bases(cls, supervisor: dict, content_base_uuid: str, project_uuid: str) -> list[dict]:
        combined_filter = {
            "andAll": [
                {"equals": {"key": "contentBaseUuid", "value": str(content_base_uuid)}},
                {"equals": {"key": "x-amz-bedrock-kb-data-source-id", "value": get_datasource_id(project_uuid)}},
            ]
        }

        retrieval_configuration = {"vectorSearchConfiguration": {"filter": combined_filter}}

        knowledge = supervisor["knowledge_bases"][0]

        knowledge.update({"retrievalConfiguration": retrieval_configuration})

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
        contact_id: str,
        contact_name: str = "",
        channel_uuid: str = "",
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

        instruction = (
            instruction.replace("{{DATE_TIME_NOW}}", date_time_now)
            .replace("{{CONTACT_FIELDS}}", contact_fields)
            .replace("{{SUPERVISOR_NAME}}", supervisor_name)
            .replace("{{SUPERVISOR_ROLE}}", supervisor_role)
            .replace("{{SUPERVISOR_GOAL}}", supervisor_goal)
            .replace("{{SUPERVISOR_ADJECTIVE}}", supervisor_adjective)
            .replace("{{SUPERVISOR_INSTRUCTIONS}}", supervisor_instructions)
            .replace("{{BUSINESS_RULES}}", business_rules)
            .replace("{{PROJECT_ID}}", project_id)
            .replace("{{CONTACT_ID}}", contact_id)
            .replace("{{CONTACT_NAME}}", contact_name)
            .replace("{{CHANNEL_UUID}}", channel_uuid)
            .replace("\r\n", "\n")
        )

        return instruction

    @classmethod
    def _get_guardrails(cls, project_uuid: str) -> list[dict]:
        try:
            guardrails = Guardrail.objects.get(project__uuid=project_uuid)
        except Guardrail.DoesNotExist:
            guardrails = Guardrail.objects.filter(current_version=True).order_by("created_on").last()

        if guardrails is None:
            return None

        return {"guardrailIdentifier": guardrails.identifier, "guardrailVersion": str(guardrails.version)}

    @classmethod
    def __get_prompt_override_configuration(self, prompt_override_configuration, use_components: bool) -> dict:
        if use_components:
            return prompt_override_configuration.get("components")
        return prompt_override_configuration.get("default")

    @classmethod
    def __get_collaborator_prompt_override_configuration(self) -> dict:
        return {
            "promptConfigurations": [
                {
                    "promptType": "KNOWLEDGE_BASE_RESPONSE_GENERATION",
                    "promptState": "DISABLED",
                    "promptCreationMode": "DEFAULT",
                    "parserMode": "DEFAULT",
                },
                {
                    "promptType": "PRE_PROCESSING",
                    "promptState": "DISABLED",
                    "promptCreationMode": "DEFAULT",
                    "parserMode": "DEFAULT",
                },
                {
                    "promptType": "POST_PROCESSING",
                    "promptState": "DISABLED",
                    "promptCreationMode": "DEFAULT",
                    "parserMode": "DEFAULT",
                },
            ]
        }


class BedrockDataLakeEventAdapter(DataLakeEventAdapter):
    """Adapter for transforming Bedrock traces to data lake event format."""

    def __init__(self, send_data_lake_event_task: callable = None):
        if send_data_lake_event_task is None:
            send_data_lake_event_task = self._get_send_data_lake_event_task()
        self._event_service = DataLakeEventService(send_data_lake_event_task)

    def _get_send_data_lake_event_task(self) -> callable:
        return send_data_lake_event

    def _has_called_agent(self, inline_traces: dict) -> bool:
        try:
            trace = inline_traces.get("trace", {})
            orchestration = trace.get("orchestrationTrace", {})
            invocation = orchestration.get("invocationInput", {})
            agent_collaboration = invocation.get("agentCollaboratorInvocationInput", {})
            if agent_collaboration:
                return self.metadata_agent_collaboration(agent_collaboration)
            return False
        except (KeyError, AttributeError) as e:
            logger.warning(f"Error checking agent call: {str(e)}")
            sentry_sdk.set_tag("project_uuid", inline_traces.get("project_uuid", "unknown"))
            sentry_sdk.capture_exception(e)
            return False

    def _has_called_action_group(self, inline_traces: dict) -> bool:
        try:
            trace = inline_traces.get("trace", {})
            orchestration = trace.get("orchestrationTrace", {})
            invocation = orchestration.get("invocationInput", {})
            action_group = invocation.get("actionGroupInvocationInput")
            if action_group:
                return self.metadata_action_group(action_group)
            return False
        except (KeyError, AttributeError) as e:
            logger.warning(f"Error checking action group call: {str(e)}")
            sentry_sdk.set_tag("project_uuid", inline_traces.get("project_uuid", "unknown"))
            sentry_sdk.capture_exception(e)
            return False

    def metadata_agent_collaboration(self, agent_collaboration_invocation_input: dict) -> dict:
        try:
            return {
                "agent_name": agent_collaboration_invocation_input["agentCollaboratorName"],
                "input_text": agent_collaboration_invocation_input["input"]["text"],
            }
        except (KeyError, AttributeError) as e:
            logger.error(f"Error extracting agent collaboration metadata: {str(e)}")
            sentry_sdk.set_tag("project_uuid", agent_collaboration_invocation_input.get("project_uuid", "unknown"))
            sentry_sdk.capture_exception(e)
            return {"agent_name": "unknown", "input_text": "unknown"}

    def metadata_action_group(self, action_group_invocation_input: dict) -> dict:
        try:
            return {
                "tool_name": action_group_invocation_input["actionGroupName"],
                "function_name": action_group_invocation_input["function"],
                "parameters": action_group_invocation_input["parameters"],
            }
        except (KeyError, AttributeError) as e:
            logger.error(f"Error extracting action group metadata: {str(e)}")
            sentry_sdk.set_tag("project_uuid", action_group_invocation_input.get("project_uuid", "unknown"))
            sentry_sdk.capture_exception(e)
            return {"tool_name": "unknown", "function_name": "unknown", "parameters": []}

    def to_data_lake_event(
        self,
        inline_trace: dict,
        project_uuid: str,
        contact_urn: str,
        preview: bool = False,
        backend: str = "bedrock",
        foundation_model: str = "",
        channel_uuid: Optional[str] = None,
        conversation: Optional[object] = None,
    ) -> Optional[dict]:
        if preview:
            return None

        try:
            has_agent = self._has_called_agent(inline_trace)
            has_action_group = self._has_called_action_group(inline_trace)

            if not (has_agent or has_action_group):
                logger.debug("No agent or action group found in trace")
                return None

            event_data = {
                "event_name": "weni_nexus_data",
                "date": pendulum.now("America/Sao_Paulo").to_iso8601_string(),
                "project": project_uuid,
                "contact_urn": contact_urn,
                "value_type": "string",
                "metadata": {"backend": backend, "foundation_model": foundation_model},
            }

            # Extract agent_identifier for agent_uuid lookup
            agent_identifier = None
            if has_agent:
                agent_identifier = has_agent.get("agent_name")

            if has_action_group:
                event_data["metadata"]["tool_call"] = has_action_group
                event_data["key"] = "tool_call"
                event_data["value"] = has_action_group["tool_name"]

                # Validate and send event
                validated_event = self._event_service.send_validated_event(
                    event_data=event_data,
                    project_uuid=project_uuid,
                    contact_urn=contact_urn,
                    use_delay=False,
                    channel_uuid=channel_uuid,
                    agent_identifier=agent_identifier,
                    conversation=conversation,
                )
                return validated_event

            if has_agent:
                event_data["metadata"]["agent_collaboration"] = has_agent
                event_data["key"] = "agent_invocation"
                event_data["value"] = has_agent["agent_name"]

                # Validate and send event
                validated_event = self._event_service.send_validated_event(
                    event_data=event_data,
                    project_uuid=project_uuid,
                    contact_urn=contact_urn,
                    use_delay=True,
                    channel_uuid=channel_uuid,
                    agent_identifier=agent_identifier,
                    conversation=conversation,
                )
                return validated_event

        except Exception as e:
            logger.error(f"Error processing data lake event: {str(e)}")
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.capture_exception(e)
            return None

    def custom_event_data(
        self,
        inline_trace: dict,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: str,
        collaborator_name: str = "",
        preview: bool = False,
        conversation: Optional[object] = None,
    ):
        """Delegate custom event processing to the service."""
        trace_data = {
            **inline_trace,
            "collaborator_name": collaborator_name,
            "project_uuid": project_uuid,
            "contact_urn": contact_urn,
        }
        extractor = BedrockEventExtractor()
        self._event_service.process_custom_events(
            trace_data=trace_data,
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            extractor=extractor,
            preview=preview,
            conversation=conversation,
        )

    def to_data_lake_custom_event(
        self,
        event_data: dict,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: Optional[str] = None,
        conversation: Optional[object] = None,
    ) -> Optional[dict]:
        """Send a single custom event to data lake (for direct event sending, not from traces)."""
        return self._event_service.send_custom_event(
            event_data=event_data,
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            conversation=conversation,
        )


@celery_app.task
def send_data_lake_event(event_data: dict):
    try:
        logger.info(f"Sending event data: {event_data}")
        response = send_event_data(EventPath, event_data)
        logger.info(f"Successfully sent data lake event: {response}")
        return response
    except Exception as e:
        logger.error(f"Failed to send data lake event: {str(e)}")
        sentry_sdk.set_tag("project_uuid", event_data.get("project", "unknown"))
        sentry_sdk.set_context("event_data", event_data)
        sentry_sdk.capture_exception(e)
        raise
