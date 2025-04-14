from typing import Dict

from django.conf import settings

from nexus.inline_agents.models import Agent, AgentCredential
from nexus.internals.flows import FlowsRESTClient
from nexus.projects.models import Project
from nexus.usecases.inline_agents.bedrock import BedrockClient
from nexus.usecases.inline_agents.tools import ToolsUseCase


class CreateAgentUseCase(ToolsUseCase):
    def __init__(self, agent_backend_client = BedrockClient):
        self.agent_backend_client = agent_backend_client()

    def create_agent(self, agent_key: str, agent: dict, project: Project, files: dict):
        print(f"[+ 🧠 Creating agent {agent_key} +]")
        instructions_guardrails = agent["instructions"] + agent["guardrails"]
        instructions = "\n".join(instructions_guardrails)
        agent_obj = Agent.objects.create(
            name=agent["name"],
            slug=agent_key,
            collaboration_instructions=agent["description"],
            project=project,
            instruction=instructions,
            foundation_model=settings.AWS_BEDROCK_AGENTS_MODEL_ID,
        )
        self.handle_tools(agent_obj, project, agent["tools"], files, str(project.uuid))
        self.create_credentials(agent_obj, project, agent["credentials"])
        print(f"[+ 🧠 Created agent {agent_key} +]")
        return agent_obj

    def create_credentials(self, agent: Agent, project: Project, credentials: Dict):
        if not credentials:
            return

        for key, credential in credentials.items():
            print(f"[+ 🧠 Creating credential {key} +]")
            is_confidential = credential.get('is_confidential', True)

            AgentCredential.objects.create(
                agent=agent,
                project=project,
                key=key,
                label=credential.get('label', key),
                placeholder=credential.get('placeholder', ''),
                is_confidential=is_confidential
            )
