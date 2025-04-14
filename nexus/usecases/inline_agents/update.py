import boto3

from django.conf import settings
from django.template.defaultfilters import slugify

from io import BytesIO

from nexus.inline_agents.models import Agent, AgentCredential, ContactField
from nexus.projects.models import Project
from typing import Dict, List
from nexus.internals.flows import FlowsRESTClient
from nexus.usecases.inline_agents.bedrock import BedrockClient
from nexus.usecases.inline_agents.tools import ToolsUseCase


class UpdateAgentUseCase(ToolsUseCase):
    def __init__(self, agent_backend_client = BedrockClient):
        self.agent_backend_client = agent_backend_client()

    def update_agent(self, agent_obj: Agent, agent_data: dict, project: Project, files: dict):
        instructions_guardrails = agent_data.get("instructions", []) + agent_data.get("guardrails", [])
        instructions = "\n".join(instructions_guardrails)

        agent_obj.name = agent_data["name"]
        agent_obj.collaboration_instructions = agent_data["description"]
        agent_obj.instruction = instructions
        agent_obj.foundation_model = settings.AWS_BEDROCK_AGENTS_MODEL_ID
        agent_obj.save()

        self.handle_tools(agent_obj, project, agent_data["tools"], files, str(project.uuid))
        self.update_credentials(agent_obj, project, agent_data.get("credentials", {}))

        return agent_data

    def update_credentials(self, agent: Agent, project: Project, credentials: Dict):
        if not credentials:
            agent.inline_credentials.all().delete()
            return

        existing_credentials = {
            cred.key: cred for cred in agent.inline_credentials.filter(project=project)
        }

        for key, credential in credentials.items():
            is_confidential = credential.get('is_confidential', True)
            
            if key in existing_credentials:
                print(f"[+ 🧠 Updating credential {key} +]")
                cred = existing_credentials[key]
                cred.label = credential.get('label', key)
                cred.placeholder = credential.get('placeholder', '')
                cred.is_confidential = is_confidential
                cred.save()
                del existing_credentials[key]
            else:
                print(f"[+ 🧠 Creating credential {key} +]")
                AgentCredential.objects.create(
                    agent=agent,
                    project=project,
                    key=key,
                    label=credential.get('label', key),
                    placeholder=credential.get('placeholder', ''),
                    is_confidential=is_confidential
                )

        for cred in existing_credentials.values():
            print(f"[+ 🧠 Deleting credential {cred.key} +]")
            cred.delete()
