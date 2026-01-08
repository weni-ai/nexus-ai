from typing import Optional, Tuple

from nexus.inline_agents.models import Agent, AgentCredential, IntegratedAgent
from nexus.projects.models import Project


class AssignAgentsUsecase:
    def assign_agent(self, agent_uuid: str, project_uuid: str) -> Tuple[bool, IntegratedAgent]:
        try:
            agent = Agent.objects.get(uuid=agent_uuid)
            project = Project.objects.get(uuid=project_uuid)
            integrated_agent, created = IntegratedAgent.objects.get_or_create(
                agent=agent,
                project=project,
                defaults={"metadata": {}},
            )
            return created, integrated_agent
        except Agent.DoesNotExist as e:
            raise ValueError("Agent not found") from e
        except Project.DoesNotExist as e:
            raise ValueError("Project not found") from e

    def unassign_agent(self, agent_uuid: str, project_uuid: str) -> Tuple[bool, Optional[IntegratedAgent]]:
        try:
            agent = Agent.objects.get(uuid=agent_uuid)
            project = Project.objects.get(uuid=project_uuid)
            try:
                integrated_agent = IntegratedAgent.objects.get(agent=agent, project=project)
                deleted_agent = integrated_agent
                integrated_agent.delete()

                for cred in AgentCredential.objects.filter(agents=agent, project=project):
                    cred.agents.remove(agent)
                    if len(cred.agents.all()) == 0:
                        cred.delete()

                return True, deleted_agent
            except IntegratedAgent.DoesNotExist:
                return False, None
        except Agent.DoesNotExist as e:
            raise ValueError("Agent not found") from e
        except Project.DoesNotExist as e:
            raise ValueError("Project not found") from e
