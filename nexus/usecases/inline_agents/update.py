from django.conf import settings

from nexus.agents.encryption import encrypt_value
from nexus.inline_agents.models import Agent, AgentCredential

from nexus.projects.models import Project

from nexus.usecases.inline_agents.bedrock import BedrockClient
from nexus.usecases.inline_agents.tools import ToolsUseCase
from nexus.usecases.inline_agents.instructions import InstructionsUseCase

from typing import Dict


class UpdateAgentUseCase(ToolsUseCase, InstructionsUseCase):
    def __init__(self, agent_backend_client=BedrockClient):
        self.agent_backend_client = agent_backend_client()

    def update_agent(self, agent_obj: Agent, agent_data: dict, project: Project, files: dict):
        instructions: str = self.handle_instructions(
            agent_data.get("instructions", []),
            agent_data.get("guardrails", []),
            agent_data.get("components", [])
        )

        agent_obj.name = agent_data["name"]
        agent_obj.collaboration_instructions = agent_data["description"]
        agent_obj.instruction = instructions
        agent_obj.foundation_model = settings.AWS_BEDROCK_AGENTS_MODEL_ID[0]
        agent_obj.save()

        self.handle_tools(agent_obj, project, agent_data["tools"], files, str(project.uuid))
        self.update_credentials(agent_obj, project, agent_data.get("credentials", {}))

        return agent_data

    def update_credentials(self, agent: Agent, project: Project, credentials: Dict):
        if not credentials:
            if hasattr(agent, 'inline_credentials'):
                agent.inline_credentials.all().delete()
            return

        existing_credentials = {
            cred.key: cred for cred in AgentCredential.objects.filter(project=project, agents__in=[agent])
        }
        print(f"existing_credentials: {existing_credentials}")
        for key, credential in credentials.items():
            is_confidential = credential.get('is_confidential', True)

            if key in existing_credentials:
                print(f"[+ 🧠 Updating credential {key} +]")
                cred = existing_credentials[key]
                cred.label = credential.get('label', key)
                cred.placeholder = credential.get('placeholder', '')
                cred.is_confidential = is_confidential
                cred.save()
                if agent not in cred.agents.all():
                    cred.agents.add(agent)
                del existing_credentials[key]
            else:
                print(f"[+ 🧠 Creating credential {key} +]")
                cred = AgentCredential.objects.create(
                    project=project,
                    key=key,
                    label=credential.get('label', key),
                    placeholder=credential.get('placeholder', ''),
                    is_confidential=is_confidential
                )
                cred.agents.add(agent)

        for cred in existing_credentials.values():
            agents = list(cred.agents.all())
            print(f"agents: {agents}")
            if len(agents) <= 0:
                print(f"[+ 🧠 Deleting empty credential {cred.key} {project.uuid} +]")
                cred.delete()
            elif len(agents) == 1 and agent in agents:
                print(f"[+ 🧠 Deleting credential {cred.key} {project.uuid} +]")
                cred.delete()
            elif agent in agents:
                print(f"[+ 🧠 Removing agent {agent.name} from credential {cred.key} {project.uuid} +]")
                cred.agents.remove(agent)

    def update_credential_value(self, project_uuid: str, key: str, value: str) -> bool:
        try:
            credential = AgentCredential.objects.get(project__uuid=project_uuid, key=key)
            credential.value = encrypt_value(value) if credential.is_confidential else value
            credential.save()
            return True
        except AgentCredential.DoesNotExist:
            return False
