import logging
from typing import Optional, Tuple

import pendulum
from django.db.models import Prefetch

from nexus.event_domain.recent_activity.create import create_recent_activity
from nexus.event_domain.recent_activity.recent_activities_dto import CreateRecentActivityDTO
from nexus.event_domain.recent_activity.recent_activity_amq import schedule_notify_change
from nexus.inline_agents.models import MCP, Agent, AgentCredential, IntegratedAgent
from nexus.intelligences.models import IntegratedIntelligence
from nexus.projects.models import Project
from nexus.users.models import User

logger = logging.getLogger(__name__)


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


def _publish_assignment_change_history(
    *,
    agent: Agent,
    project: Project,
    action_type: str,
    user: Optional[User] = None,
) -> None:
    created_by = user or project.created_by
    if created_by is None:
        logger.warning(
            "Skipping agent assignment change history: missing user for project %s",
            project.uuid,
        )
        return

    try:
        integrated = IntegratedIntelligence.objects.filter(project=project).select_related("intelligence").first()
        if integrated is not None:
            create_recent_activity(
                instance=agent,
                dto=CreateRecentActivityDTO(
                    action_type=action_type,
                    project=project,
                    created_by=created_by,
                    intelligence=integrated.intelligence,
                    action_details={},
                ),
            )
            return

        action_by_type = {"C": "CREATE", "D": "DELETE"}
        action = action_by_type.get(action_type)
        if action is None:
            logger.warning(
                "Unexpected action_type %r for agent assignment change history",
                action_type,
            )
            return

        schedule_notify_change(
            project_uuid=str(project.uuid),
            user_email=created_by.email,
            date=pendulum.now("UTC"),
            action=action,
            entity="Agent",
            object_id=str(agent.uuid),
            object_name=agent.name,
        )
    except Exception:
        logger.exception(
            "Failed to publish agent assignment change history for agent=%s project=%s",
            getattr(agent, "uuid", None),
            getattr(project, "uuid", None),
        )


class AssignAgentsUsecase:
    def assign_agent(
        self,
        agent_uuid: str,
        project_uuid: str,
        *,
        infer_mcp_metadata: bool = False,
        user: Optional[User] = None,
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
            reactivated = False
            if not created and not integrated_agent.is_active:
                integrated_agent.is_active = True
                integrated_agent.save(update_fields=["is_active"])
                reactivated = True
            if infer_mcp_metadata and _apply_unique_mcp_metadata_to_integrated_agent(integrated_agent, agent):
                integrated_agent.save(update_fields=["metadata"])
            if created or reactivated:
                _publish_assignment_change_history(
                    agent=agent,
                    project=project,
                    action_type="C",
                    user=user,
                )
            return created, integrated_agent
        except Agent.DoesNotExist as e:
            raise ValueError("Agent not found") from e
        except Project.DoesNotExist as e:
            raise ValueError("Project not found") from e

    def unassign_agent(
        self,
        agent_uuid: str,
        project_uuid: str,
        *,
        user: Optional[User] = None,
    ) -> Tuple[bool, Optional[IntegratedAgent]]:
        try:
            agent = Agent.objects.get(uuid=agent_uuid)
            project = Project.objects.get(uuid=project_uuid)
            try:
                integrated_agent = IntegratedAgent.objects.get(agent=agent, project=project)
                deleted_agent = integrated_agent
                integrated_agent.delete()
                _clear_agent_credential_values_on_unassign(agent, project)
                _publish_assignment_change_history(
                    agent=agent,
                    project=project,
                    action_type="D",
                    user=user,
                )
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
