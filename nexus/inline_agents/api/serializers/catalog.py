from __future__ import annotations

from typing import Any

from django.core.exceptions import ObjectDoesNotExist

from nexus.inline_agents.api.official_agents_helpers import (
    _serialize_mcp,
    _sort_mcps,
    get_all_mcps_for_group,
    get_all_systems_for_group,
)
from nexus.inline_agents.models import Agent, IntegratedAgent


def _catalog_display_name(agent: Agent) -> str:
    """User-facing label: group modal catalog name or group name, else template name trimmed."""
    if not getattr(agent, "group_id", None):
        raw = agent.name
        return raw.split("(")[0].strip() if "(" in raw else raw
    group = agent.group
    try:
        modal = group.modal
        if modal.agent_name:
            return modal.agent_name
    except ObjectDoesNotExist:
        pass
    return group.name


def _category_slug(agent: Agent) -> str | None:
    cat = getattr(agent, "category", None)
    return cat.slug if cat else None


def _about_payload(agent: Agent) -> dict[str, str | None]:
    """Localized about: modal fields when set, else fallback agent description in ``en`` only."""
    group = getattr(agent, "group", None)
    if not group:
        desc = (agent.collaboration_instructions or "").strip() or None
        return {"en": desc, "pt": None, "es": None}
    try:
        modal = group.modal
        en = (modal.about_en or "").strip() or None
        pt = (modal.about_pt or "").strip() or None
        es = (modal.about_es or "").strip() or None
        if not any([en, pt, es]):
            desc = (agent.collaboration_instructions or "").strip() or None
            return {"en": desc, "pt": None, "es": None}
        return {"en": en, "pt": pt, "es": es}
    except ObjectDoesNotExist:
        desc = (agent.collaboration_instructions or "").strip() or None
        return {"en": desc, "pt": None, "es": None}


def _conversation_example_payload(agent: Agent) -> dict[str, Any] | None:
    group = getattr(agent, "group", None)
    if not group:
        return None
    try:
        modal = group.modal
        return {
            "en": list(modal.conversation_example_en or []),
            "pt": list(modal.conversation_example_pt or []),
            "es": list(modal.conversation_example_es or []),
        }
    except ObjectDoesNotExist:
        return None


def _flatten_group_mcps(group_slug: str) -> list[dict[str, Any]]:
    by_system = get_all_mcps_for_group(group_slug)
    out: list[dict[str, Any]] = []
    for system_slug in sorted(by_system.keys(), key=lambda s: (0 if str(s).lower() == "vtex" else 1, str(s).lower())):
        out.extend(by_system[system_slug])
    return _sort_mcps(out)


def _mcps_for_standalone_agent(agent: Agent) -> list[dict[str, Any]]:
    mcps = (
        agent.mcps.filter(is_active=True)
        .select_related("system")
        .prefetch_related("config_options", "credential_templates")
    )
    return _sort_mcps([_serialize_mcp(m) for m in mcps])


def build_row_from_integrated(integrated: IntegratedAgent) -> dict[str, Any]:
    """Team roster row: one ``IntegratedAgent`` as novo retorno."""
    agent = integrated.agent
    group = getattr(agent, "group", None)
    group_slug = group.slug if group else None
    systems = [s.slug for s in agent.systems.all()]
    if group_slug:
        mcps = _flatten_group_mcps(group_slug)
    else:
        mcps = _mcps_for_standalone_agent(agent)
    return {
        "group": group_slug,
        "name": _catalog_display_name(agent),
        "slug": agent.slug,
        "uuid": str(agent.uuid),
        "about": _about_payload(agent),
        "assigned": True,
        "active": integrated.is_active,
        "is_official": agent.is_official,
        "category": _category_slug(agent),
        "systems": systems,
        "mcps": mcps,
        "conversation_example": _conversation_example_payload(agent),
        "agents": None,
    }


def build_row_from_project_agent(
    agent: Agent,
    project_uuid: str | None,
    *,
    include_inactive_integrated: bool = False,
) -> dict[str, Any]:
    """My-agents / project catalog row for an ``Agent`` owned by the project."""
    group = getattr(agent, "group", None)
    group_slug = group.slug if group else None
    systems = [s.slug for s in agent.systems.all()]
    if group_slug:
        mcps = _flatten_group_mcps(group_slug)
    else:
        mcps = _mcps_for_standalone_agent(agent)

    assigned = False
    active: bool | None = None
    if project_uuid:
        qs_all = IntegratedAgent.objects.filter(project_id=project_uuid, agent=agent)
        qs_active = qs_all.filter(is_active=True)
        if include_inactive_integrated:
            assigned = qs_all.exists()
        else:
            assigned = qs_active.exists()
        integrated = qs_all.first()
        active = integrated.is_active if integrated else False
    else:
        active = None

    return {
        "group": group_slug,
        "name": _catalog_display_name(agent),
        "slug": agent.slug,
        "uuid": str(agent.uuid),
        "about": _about_payload(agent),
        "assigned": assigned,
        "active": active,
        "is_official": agent.is_official,
        "category": _category_slug(agent),
        "systems": systems,
        "mcps": mcps,
        "conversation_example": _conversation_example_payload(agent),
        "agents": None,
    }


def _integrated_assignment_flags(project_uuid: str | None, agent_uuids: list) -> tuple[bool, bool | None]:
    """``assigned`` = any active IA; ``active`` = any IA exists with states as in product rules."""
    if not project_uuid or not agent_uuids:
        return False, None
    qs = IntegratedAgent.objects.filter(project__uuid=project_uuid, agent__uuid__in=agent_uuids)
    has_active = qs.filter(is_active=True).exists()
    has_any = qs.exists()
    assigned = has_active
    if not has_any:
        active: bool | None = None
    elif has_active:
        active = True
    else:
        active = False
    return assigned, active


def _member_row(agent: Agent, project_uuid: str | None) -> dict[str, Any]:
    assigned = False
    active: bool | None = None
    if project_uuid:
        ia = (
            IntegratedAgent.objects.filter(project__uuid=project_uuid, agent=agent)
            .order_by("-is_active", "-id")
            .first()
        )
        if ia:
            active = ia.is_active
            assigned = ia.is_active
    systems = [s.slug for s in agent.systems.all()]
    return {
        "uuid": str(agent.uuid),
        "name": agent.name,
        "slug": agent.slug,
        "systems": systems,
        "assigned": assigned,
        "active": active,
    }


def build_official_group_row(
    group_agents: list[Agent],
    group_slug: str,
    project_uuid: str | None,
) -> dict[str, Any]:
    """One catalog row per official ``AgentGroup`` (novo retorno)."""
    group_agents = sorted(group_agents, key=lambda a: (a.name, str(a.uuid)))
    base = group_agents[0]
    display_name = _catalog_display_name(base)
    systems_sorted = sorted(
        get_all_systems_for_group(group_slug),
        key=lambda s: (0 if "vtex" in str(s).lower() else 1, str(s).lower()),
    )
    agent_uuids = [a.uuid for a in group_agents]
    assigned, active = _integrated_assignment_flags(project_uuid, agent_uuids)
    mcps = _flatten_group_mcps(group_slug)
    inner_agents = [_member_row(a, project_uuid) for a in group_agents]

    return {
        "group": group_slug,
        "name": display_name,
        "slug": base.slug,
        "uuid": str(base.uuid),
        "about": _about_payload(base),
        "assigned": assigned,
        "active": active,
        "is_official": base.is_official,
        "category": _category_slug(base),
        "systems": systems_sorted,
        "mcps": mcps,
        "conversation_example": _conversation_example_payload(base),
        "agents": inner_agents,
    }
