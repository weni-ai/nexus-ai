from typing import Dict

from django.conf import settings

from nexus.agents.encryption import encrypt_value

from nexus.inline_agents.models import Agent, AgentCredential
from nexus.projects.models import Project
from nexus.usecases.inline_agents.bedrock import BedrockClient
from nexus.usecases.inline_agents.tools import ToolsUseCase
from nexus.usecases.inline_agents.instructions import InstructionsUseCase
from nexus.intelligences.models import Conversation, ConversationMessage, Topics
from nexus.inline_agents.models import InlineAgentMessage

class CreateAgentUseCase(ToolsUseCase, InstructionsUseCase):
    def __init__(self, agent_backend_client=BedrockClient):
        self.agent_backend_client = agent_backend_client()

    def create_agent(self, agent_key: str, agent: dict, project: Project, files: dict):
        print(f"[+ 🧠 Creating agent {agent_key} +]")
        instructions: str = self.handle_instructions(
            agent.get("instructions", []),
            agent.get("guardrails", []),
            agent.get("components", [])
        )
        agent_obj = Agent.objects.create(
            name=agent["name"],
            slug=agent_key,
            collaboration_instructions=agent["description"],
            project=project,
            instruction=instructions,
            foundation_model=settings.AWS_BEDROCK_AGENTS_MODEL_ID[0],
        )
        self.handle_tools(agent_obj, project, agent["tools"], files, str(project.uuid))
        self.create_credentials(agent_obj, project, agent.get("credentials", {}))
        print(f"[+ 🧠 Created agent {agent_key} +]")
        return agent_obj

    def create_credentials(self, agent: Agent, project: Project, credentials: Dict):
        created_credentials = []
        if not credentials:
            return

        for key, credential in credentials.items():
            print(f"[+ 🧠 Creating credential {key} +]")
            is_confidential = credential.get('is_confidential', True)

            existing_credential = AgentCredential.objects.filter(
                project=project,
                key=key
            )

            credential_value = encrypt_value(credential.get('value')) if is_confidential else credential.get('value')

            if existing_credential.exists():
                existing_credential = existing_credential.first()
                print(f"[+ 🧠 Updating existing credential {key} +]")
                existing_credential.label = credential.get('label', key)
                existing_credential.placeholder = credential.get('placeholder', '')
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
                    label=credential.get('label', key),
                    placeholder=credential.get('placeholder', ''),
                    is_confidential=is_confidential,
                    value=credential_value if credential_value else "",
                )
                new_credential.agents.add(agent)

            created_credentials.append(key)

        return created_credentials


class CreateConversationUseCase():

    def create_conversation(self, consumer_message: dict):
        messages = InlineAgentMessage.objects.filter(
            created_at__gte=consumer_message.get("start_date"),
            created_at__lte=consumer_message.get("end_date"),
            contact_urn=consumer_message.get("contact_urn")
        )

        if not messages.exists():
            return
        project = Project.objects.get(uuid=consumer_message.get("project_uuid"))

        conversation = Conversation.objects.create(
            project=project,
            external_id=consumer_message.get("external_id"),
            has_chats_room=consumer_message.get("has_chats_room"),
            contact_urn=consumer_message.get("contact_urn")
        )

        ConversationMessage.objects.create(
            conversation=conversation,
            message=messages
        )

        return conversation