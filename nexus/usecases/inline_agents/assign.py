from typing import Optional, Tuple

from django.db.models import Prefetch

from nexus.inline_agents.models import MCP, Agent, AgentCredential, IntegratedAgent
from nexus.projects.models import Project


def infer_single_active_mcp_selection(agent: Agent) -> tuple[str | None, str | None]:
    """Return (mcp_name, system_slug) when the agent has exactly one active MCP."""
    prefetched = getattr(agent, "_prefetched_objects_cache", {}).get("mcps")
    if prefetched is None:
        mcps = list(agent.mcps.filter(is_active=True).select_related("system"))
    else:
        mcps = [mcp for mcp in prefetched if mcp.is_active]

    if len(mcps) != 1:
        return None, None

    mcp = mcps[0]
    system_slug = mcp.system.slug if mcp.system_id else None
    return mcp.name, system_slug


def resolve_assignment_mcp_fields(
    agent: Agent,
    mcp: str | None,
    mcp_config: dict | None,
    system: str | None,
) -> tuple[str | None, dict | None, str | None]:
    """Infer MCP/system when only constants (``mcp_config``) are sent for a single-MCP agent."""
    config = mcp_config or {}
    if mcp or not config:
        return mcp, config or None, system

    inferred_mcp, inferred_system = infer_single_active_mcp_selection(agent)
    if inferred_mcp:
        mcp = inferred_mcp
        if not system and inferred_system:
            system = inferred_system
    return mcp, config, system


def _clear_agent_credential_values_on_unassign(agent: Agent, project: Project) -> None:
    """Clear stored secret values for credentials linked to the agent, keeping schema rows."""
    for cred in AgentCredential.objects.filter(agents=agent, project=project):
        other_agents_still_assigned = IntegratedAgent.objects.filter(
            project=project,
            agent__in=cred.agents.exclude(pk=agent.pk),
        ).exists()
        if other_agents_still_assigned or not cred.value:
            continue
        cred.value = ""
        cred.save(update_fields=["value"])


def _apply_unique_mcp_metadata_to_integrated_agent(integrated_agent: IntegratedAgent, agent: Agent) -> bool:
    """When the agent has exactly one active MCP, set metadata mcp/system (same keys as v1 official assign)."""
    prefetched = getattr(agent, "_prefetched_objects_cache", {}).get("mcps")
    if prefetched is None:
        mcps = list(agent.mcps.filter(is_active=True).select_related("system"))
    else:
        mcps = [mcp for mcp in prefetched if mcp.is_active]

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
                _clear_agent_credential_values_on_unassign(agent, project)

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
