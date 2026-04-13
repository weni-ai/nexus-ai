from typing import Optional, Tuple

from django.db.models import Prefetch

from nexus.inline_agents.models import MCP, Agent, AgentCredential, IntegratedAgent
from nexus.projects.models import Project


def _apply_unique_mcp_metadata_to_integrated_agent(integrated_agent: IntegratedAgent, agent: Agent) -> bool:
    """When the agent has exactly one active MCP, set metadata mcp/system (same keys as v1 official assign)."""
    prefetched = getattr(agent, "_prefetched_objects_cache", {}).get("mcps")
    if prefetched is None:
        mcps = list(agent.mcps.filter(is_active=True).select_related("system"))
    else:
        mcps = [m for m in prefetched if m.is_active]

    if len(mcps) != 1:
        return False

    mcp = mcps[0]
    if integrated_agent.metadata is None:
        integrated_agent.metadata = {}

    integrated_agent.metadata["mcp"] = mcp.name
    if not mcp.system_id:
        integrated_agent.metadata.pop("system", None)
    else:
        integrated_agent.metadata["system"] = mcp.system.slug
    return True


class AssignAgentsUsecase:
    def assign_agent(
        self, agent_uuid: str, project_uuid: str, *, infer_mcp_metadata: bool = False
    ) -> Tuple[bool, IntegratedAgent]:
        try:
            if infer_mcp_metadata:
                agent = Agent.objects.prefetch_related(
                    Prefetch("mcps", queryset=MCP.objects.filter(is_active=True).select_related("system"))
                ).get(uuid=agent_uuid)
            else:
                agent = Agent.objects.get(uuid=agent_uuid)
            project = Project.objects.get(uuid=project_uuid)
            integrated_agent, created = IntegratedAgent.objects.get_or_create(
                agent=agent,
                project=project,
                defaults={"metadata": {}, "is_active": True},
            )
            if not created and not integrated_agent.is_active:
                integrated_agent.is_active = True
                integrated_agent.save(update_fields=["is_active"])
            if infer_mcp_metadata and _apply_unique_mcp_metadata_to_integrated_agent(integrated_agent, agent):
                integrated_agent.save(update_fields=["metadata"])
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

    def set_agent_active(self, agent_uuid: str, project_uuid: str, active: bool) -> IntegratedAgent:
        integrated_agent = IntegratedAgent.objects.get(
            agent__uuid=agent_uuid,
            project__uuid=project_uuid,
        )
        integrated_agent.is_active = active
        integrated_agent.save(update_fields=["is_active"])
        return integrated_agent
