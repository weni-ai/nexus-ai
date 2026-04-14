import logging
from typing import Dict

from nexus.agents.encryption import encrypt_value
from nexus.events import notify_async
from nexus.inline_agents.models import (
    MCP,
    Agent,
    AgentCredential,
    AgentGroup,
    InlineAgentMessage,
    IntegratedAgent,
)
from nexus.intelligences.models import Conversation
from nexus.projects.models import Project
from nexus.usecases.inline_agents.bedrock import BedrockClient
from nexus.usecases.inline_agents.instructions import InstructionsUseCase
from nexus.usecases.inline_agents.mcp_definition_sync import sync_mcp_templates_from_agent_payload
from nexus.usecases.inline_agents.tools import ToolsUseCase

logger = logging.getLogger(__name__)


def invalidate_team_cache_for_agent_integration_projects(agent: Agent) -> None:
    """Invalidate router team cache for the agent's owner project and all active integrations.

    Shared official agents are updated once in the DB; each consuming project has its own
    Redis team (and composite) keys. Push previously only cleared the pushed project.
    """
    project_uuids: set[str] = set()
    if agent.project_id:
        project_uuids.add(str(agent.project.uuid))
    for pu in IntegratedAgent.objects.filter(agent=agent, is_active=True).values_list("project__uuid", flat=True):
        project_uuids.add(str(pu))
    for project_uuid in project_uuids:
        notify_async(
            event="cache_invalidation:team",
            project_uuid=project_uuid,
        )


class UpdateAgentUseCase(ToolsUseCase, InstructionsUseCase):
    def __init__(self, agent_backend_client=BedrockClient):
        self.agent_backend_client = agent_backend_client()

    def update_agent(self, agent_obj: Agent, agent_data: dict, project: Project, files: dict):
        instructions: str = self.handle_instructions(
            agent_data.get("instructions", []), agent_data.get("guardrails", []), agent_data.get("components", [])
        )

        agent_obj.name = agent_data["name"]
        agent_obj.collaboration_instructions = agent_data["description"]
        agent_obj.instruction = instructions
        agent_obj.save()

        self.handle_tools(agent_obj, project, agent_data["tools"], files, str(project.uuid))
        self.update_credentials(agent_obj, project, agent_data.get("credentials", {}))

        old_group = agent_obj.group

        if "group" in agent_data:
            group_slug = agent_data.get("group")
            if group_slug:
                group = AgentGroup.objects.filter(slug=group_slug).first()
                agent_obj.group = group
            else:
                agent_obj.group = None
            agent_obj.save()

        if "mcps" in agent_data or "mcp" in agent_data:
            mcps_data = agent_data.get("mcps")
            if mcps_data is None:
                mcps_data = []
            elif isinstance(mcps_data, str):
                mcps_data = [mcps_data]

            if not mcps_data and "mcp" in agent_data:
                mcp_val = agent_data["mcp"]
                if isinstance(mcp_val, list):
                    mcps_data = mcp_val
                elif isinstance(mcp_val, dict):
                    mcps_data = [mcp_val]
                elif isinstance(mcp_val, str) and mcp_val:
                    mcps_data = [mcp_val]

            agent_obj.mcps.clear()  # Clear existing to handle removals/updates

            for mcp_item in mcps_data:
                if isinstance(mcp_item, str):
                    mcp = MCP.objects.filter(slug=mcp_item).first()
                    if not mcp:
                        mcp = MCP.objects.create(
                            slug=mcp_item,
                            name=mcp_item,
                            system=None,
                            description_en=f"Auto-created MCP for {mcp_item}",
                        )

                    sync_mcp_templates_from_agent_payload(
                        mcp, agent_data.get("credentials"), agent_data.get("constants")
                    )

                    agent_obj.mcps.add(mcp)
                elif isinstance(mcp_item, dict):
                    slug = mcp_item.get("slug")
                    if not slug:
                        continue
                    mcp = MCP.objects.filter(slug=slug).first()
                    if not mcp:
                        continue

                    sync_mcp_templates_from_agent_payload(mcp, mcp_item.get("credentials"), mcp_item.get("constants"))

                    agent_obj.mcps.add(mcp)

        if old_group and old_group != agent_obj.group:
            old_group.update_mcps_from_agents()

        if agent_obj.group:
            agent_obj.group.update_mcps_from_agents()

        invalidate_team_cache_for_agent_integration_projects(agent_obj)

        return agent_data

    def update_credentials(self, agent: Agent, project: Project, credentials: Dict):
        if not credentials:
            if hasattr(agent, "inline_credentials"):
                agent.inline_credentials.all().delete()
            return

        existing_credentials = {cred.key: cred for cred in AgentCredential.objects.filter(project=project)}

        for key, credential in credentials.items():
            is_confidential = credential.get("is_confidential", True)

            if key in existing_credentials:
                logger.info(f"Updating credential - key: {key}")
                cred = existing_credentials[key]
                cred.label = credential.get("label", key)
                cred.placeholder = credential.get("placeholder", "")
                cred.is_confidential = is_confidential
                cred.save()
                if agent not in cred.agents.all():
                    cred.agents.add(agent)
                del existing_credentials[key]
            else:
                logger.info(f"Creating credential - key: {key}")
                cred = AgentCredential.objects.create(
                    project=project,
                    key=key,
                    label=credential.get("label", key),
                    placeholder=credential.get("placeholder", ""),
                    is_confidential=is_confidential,
                )
                cred.agents.add(agent)

        for cred in existing_credentials.values():
            agents = list(cred.agents.all())

            if len(agents) <= 0:
                logger.info(f"Deleting empty credential - key: {cred.key}, project_uuid: {str(project.uuid)}")
                cred.delete()
            elif len(agents) == 1 and agent in agents:
                logger.info(f"Deleting credential - key: {cred.key}, project_uuid: {str(project.uuid)}")
                cred.delete()
            elif agent in agents:
                cred.agents.remove(agent)

    def update_credential_value(self, project_uuid: str, key: str, value: str) -> bool:
        try:
            credential = AgentCredential.objects.get(project__uuid=project_uuid, key=key)
            credential.value = encrypt_value(value) if credential.is_confidential else value
            credential.save()
            return True
        except AgentCredential.DoesNotExist:
            return False


class UpdateConversationUseCase:
    def update_conversation(self, consumer_message: dict) -> Conversation:
        messages = InlineAgentMessage.objects.filter(
            created_at__gte=consumer_message.get("start_date"),
            created_at__lte=consumer_message.get("end_date"),
            contact_urn=consumer_message.get("contact_urn"),
        )

        if not messages.exists():
            return None
        project = Project.objects.get(uuid=consumer_message.get("project_uuid"))

        conversation = (
            Conversation.objects.filter(project=project, contact_urn=consumer_message.get("contact_urn"))
            .order_by("-created_at")
            .first()
        )
        conversation.external_id = consumer_message.get("external_id")
        conversation.has_chats_room = consumer_message.get("has_chats_room")
        conversation.start_date = consumer_message.get("start_date")
        conversation.end_date = consumer_message.get("end_date")
        conversation.contact_name = consumer_message.get("name")
        conversation.save()

        return conversation


def update_conversation_data(to_update: dict, project_uuid: str, contact_urn: str, channel_uuid: str):
    from nexus.intelligences.models import Conversation

    conversation = (
        Conversation.objects.filter(project__uuid=project_uuid, contact_urn=contact_urn, channel_uuid=channel_uuid)
        .order_by("-created_at")
        .first()
    )
    if not conversation:
        return
    for field, value in to_update.items():
        setattr(conversation, field, value)
    conversation.save()
