import logging
from typing import Dict

import sentry_sdk
from django.conf import settings

from nexus.agents.encryption import encrypt_value
from nexus.inline_agents.models import (
    MCP,
    Agent,
    AgentCredential,
    AgentGroup,
    AgentSystem,
    InlineAgentMessage,
    MCPConfigOption,
    MCPCredentialTemplate,
)
from nexus.intelligences.models import Conversation
from nexus.projects.models import Project
from nexus.usecases.inline_agents.bedrock import BedrockClient
from nexus.usecases.inline_agents.instructions import InstructionsUseCase
from nexus.usecases.inline_agents.tools import ToolsUseCase

logger = logging.getLogger(__name__)


class CreateAgentUseCase(ToolsUseCase, InstructionsUseCase):
    def __init__(self, agent_backend_client=BedrockClient):
        self.agent_backend_client = agent_backend_client()

    def create_agent(self, agent_key: str, agent: dict, project: Project, files: dict):
        logger.info(f"Creating agent - agent_key: {agent_key}")
        instructions: str = self.handle_instructions(
            agent.get("instructions", []), agent.get("guardrails", []), agent.get("components", [])
        )
        agent_obj = Agent.objects.create(
            name=agent["name"],
            slug=agent_key,
            collaboration_instructions=agent["description"],
            project=project,
            instruction=instructions,
            foundation_model=settings.AWS_BEDROCK_AGENTS_MODEL_ID[0],
            backend_foundation_models=settings.DEFAULT_FOUNDATION_MODELS,
        )
        self.handle_tools(agent_obj, project, agent["tools"], files, str(project.uuid))
        self.create_credentials(agent_obj, project, agent.get("credentials", {}))

        if agent.get("group"):
            group = AgentGroup.objects.filter(slug=agent.get("group")).first()
            if group:
                agent_obj.group = group
                agent_obj.save()

        if agent.get("mcps") or agent.get("mcp"):
            mcps_data = agent.get("mcps")
            if mcps_data is None:
                mcps_data = []
            elif isinstance(mcps_data, str):
                mcps_data = [mcps_data]

            if not mcps_data and "mcp" in agent:
                mcp_val = agent["mcp"]
                if isinstance(mcp_val, list):
                    mcps_data = mcp_val
                elif isinstance(mcp_val, dict):
                    mcps_data = [mcp_val]
                elif isinstance(mcp_val, str) and mcp_val:
                    mcps_data = [mcp_val]

            for mcp_item in mcps_data:
                if isinstance(mcp_item, str):
                    mcp = MCP.objects.filter(slug=mcp_item).first()
                    if mcp:
                        agent_obj.mcps.add(mcp)
                elif isinstance(mcp_item, dict):
                    slug = mcp_item.get("slug")
                    if not slug:
                        continue
                    mcp = MCP.objects.filter(slug=slug).first()
                    if not mcp:
                        system_slug = mcp_item.get("system")
                        system = None
                        if system_slug:
                            system = AgentSystem.objects.filter(slug=system_slug).first()

                        mcp = MCP.objects.create(
                            slug=slug,
                            name=mcp_item.get("name", slug),
                            system=system,
                            description=mcp_item.get("description", ""),
                        )

                    # Update or create config options if constants provided
                    if "constants" in mcp_item:
                        for key, value in mcp_item["constants"].items():
                            MCPConfigOption.objects.update_or_create(
                                mcp=mcp,
                                name=key,
                                defaults={
                                    "default_value": value,
                                    "label": key,
                                    "type": MCPConfigOption.TEXT,
                                },
                            )

                    # Update or create credential templates if credentials provided
                    if "credentials" in mcp_item:
                        for key, cred_data in mcp_item["credentials"].items():
                            if isinstance(cred_data, dict):
                                MCPCredentialTemplate.objects.update_or_create(
                                    mcp=mcp,
                                    name=key,
                                    defaults={
                                        "label": cred_data.get("label", key),
                                        "placeholder": cred_data.get("placeholder", ""),
                                        "is_confidential": cred_data.get("is_confidential", True),
                                    },
                                )

                    agent_obj.mcps.add(mcp)

        if agent_obj.group:
            agent_obj.group.update_mcps_from_agents()

        logger.info(f"Created agent - agent_key: {agent_key}")
        return agent_obj

    def _process_constants(self, constants: Dict) -> Dict | None:
        """Process constants from weni-cli YAML format to stored format"""
        if not constants:
            return None
        processed = {}
        for key, constant_def in constants.items():
            processed[key] = {"value": constant_def.get("default", ""), "definition": constant_def}
        return processed

    def create_credentials(self, agent: Agent, project: Project, credentials: Dict):
        created_credentials = []
        if not credentials:
            return

        for key, credential in credentials.items():
            logger.info(f"Creating credential - key: {key}")
            is_confidential = credential.get("is_confidential", True)

            existing_credential = AgentCredential.objects.filter(project=project, key=key)

            credential_value = encrypt_value(credential.get("value")) if is_confidential else credential.get("value")

            if existing_credential.exists():
                existing_credential = existing_credential.first()
                logger.info(f"Updating existing credential - key: {key}")
                existing_credential.label = credential.get("label", key)
                existing_credential.placeholder = credential.get("placeholder", "")
                existing_credential.is_confidential = is_confidential

                if credential_value:
                    existing_credential.value = credential_value

                existing_credential.save()
                if agent not in existing_credential.agents.all():
                    existing_credential.agents.add(agent)
            else:
                new_credential = AgentCredential.objects.create(
                    project=project,
                    key=key,
                    label=credential.get("label", key),
                    placeholder=credential.get("placeholder", ""),
                    is_confidential=is_confidential,
                    value=credential_value if credential_value else "",
                )
                new_credential.agents.add(agent)

            created_credentials.append(key)

        return created_credentials


class CreateConversationUseCase:
    def create_conversation(self, consumer_message: dict) -> Conversation:
        try:
            project = Project.objects.get(uuid=consumer_message.get("project_uuid"))

            messages = InlineAgentMessage.objects.filter(
                created_at__gte=consumer_message.get("start_date"),
                created_at__lte=consumer_message.get("end_date"),
                contact_urn=consumer_message.get("contact_urn"),
                project=project,
            )

            if not messages.exists():
                return None

            conversation = Conversation.objects.create(
                project=project,
                external_id=consumer_message.get("external_id"),
                has_chats_room=consumer_message.get("has_chats_room"),
                contact_urn=consumer_message.get("contact_urn"),
                start_date=consumer_message.get("start_date"),
                end_date=consumer_message.get("end_date"),
                contact_name=consumer_message.get("name"),
            )

            return conversation
        except Exception as e:
            sentry_sdk.set_context("conversation_context", {"consumer_message": consumer_message})
            sentry_sdk.capture_exception(e)
