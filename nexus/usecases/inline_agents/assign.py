from nexus.users.models import User
from typing import Tuple, Optional
from nexus.projects.models import Project
from nexus.inline_agents.models import Agent, IntegratedAgent


class AssignAgentsUsecase:
    def assign_agent(self, agent_uuid: str, project_uuid: str) -> Tuple[bool, IntegratedAgent]:
        try:
            agent = Agent.objects.get(uuid=agent_uuid)
            project = Project.objects.get(uuid=project_uuid)
            integrated_agent, created = IntegratedAgent.objects.get_or_create(
                agent=agent,
                project=project,
            )
            return created, integrated_agent
        except Agent.DoesNotExist:
            raise ValueError("Agent not found")
        except Project.DoesNotExist:
            raise ValueError("Project not found")

    def unassign_agent(self, agent_uuid: str, project_uuid: str) -> Tuple[bool, Optional[IntegratedAgent]]:
        try:
            agent = Agent.objects.get(uuid=agent_uuid)
            project = Project.objects.get(uuid=project_uuid)
            try:
                integrated_agent = IntegratedAgent.objects.get(
                    agent=agent,
                    project=project
                )
                deleted_agent = integrated_agent
                integrated_agent.delete()
                return True, deleted_agent
            except IntegratedAgent.DoesNotExist:
                return False, None
        except Agent.DoesNotExist:
            raise ValueError("Agent not found")
        except Project.DoesNotExist:
            raise ValueError("Project not found")
