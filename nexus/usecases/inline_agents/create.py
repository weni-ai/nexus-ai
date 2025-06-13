from typing import Dict

from django.conf import settings

from nexus.agents.encryption import encrypt_value

from nexus.inline_agents.models import Agent, AgentCredential
from nexus.projects.models import Project
from nexus.usecases.inline_agents.bedrock import BedrockClient
from nexus.usecases.inline_agents.tools import ToolsUseCase
from nexus.usecases.inline_agents.instructions import InstructionsUseCase


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
        print(f"instructions: {instructions}")
        agent_obj = Agent.objects.create(
            name=agent["name"],
            slug=agent_key,
            collaboration_instructions=agent["description"],
            project=project,
            instruction=instructions,
            foundation_model=settings.AWS_BEDROCK_AGENTS_MODEL_ID[0],
        )
        self.handle_tools(agent_obj, project, agent["tools"], files, str(project.uuid))
        print(f"[+ 🧠 Created agent {agent_key} +]")
        print(f"[+ 🧠 Creating agent credentials {agent.get('credentials', {})} +]")
        self.create_credentials(agent_obj, project, agent.get("credentials", {}))
        print(f"[+ 🧠 Created agent {agent_key} +]")
        return agent_obj

    def create_credentials(self, agent: Agent, project: Project, credentials: Dict):
        created_credentials = []
        if not credentials:
            return
        print(f"[+ 🧠 Creating credentials {credentials} +]")

        for key, credential in credentials.items():
            print(f"[+ 🧠 Creating credential {key} +]")
            is_confidential = credential.get('is_confidential', True)

            existing_credential = AgentCredential.objects.filter(
                project=project,
                key=key
            )
            print(f"[+ 🧠 Existing credential {existing_credential} +]")

            credential_value = encrypt_value(credential.get('value')) if is_confidential else credential.get('value')

            print(f"[+ 🧠 Credential value {credential_value} +]")

            if existing_credential.exists():
                existing_credential = existing_credential.first()
                print(f"[+ 🧠 Updating existing credential {key} +]")
                existing_credential.label = credential.get('label', key)
                existing_credential.placeholder = credential.get('placeholder', '')
                existing_credential.is_confidential = is_confidential
                print(f"[+ 🧠 Updating existing credential label {existing_credential.label} +]")
                print(f"[+ 🧠 Updating existing credential placeholder {existing_credential.placeholder} +]")
                print(f"[+ 🧠 Updating existing credential is_confidential {existing_credential.is_confidential} +]")

                if credential_value:
                    existing_credential.value = credential_value
                    print(f"[+ 🧠 Updating existing credential value {existing_credential.value} +]")

                existing_credential.save()
                print(f"[+ 🧠 Saved existing credential {existing_credential} +]")
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
                print(f"[+ 🧠 Created new credential {new_credential.__dict__} +]")
                new_credential.agents.add(agent)

            created_credentials.append(key)

        return created_credentials
