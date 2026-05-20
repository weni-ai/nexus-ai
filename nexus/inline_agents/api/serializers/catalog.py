from __future__ import annotations

from itertools import groupby
from typing import Any

from django.core.exceptions import ObjectDoesNotExist

from nexus.inline_agents.api.official_agents_helpers import (
    _serialize_mcp,
    _sort_mcps,
    _sort_systems,
    _system_bucket_sort_key,
    get_all_mcps_for_group,
    get_all_systems_for_group,
)
from nexus.inline_agents.models import Agent, IntegratedAgent

# Canonical catalog row (novo retorno) — same keys on every list surface.
# Official v1: one row per ``AgentGroup`` (group view). My-agents / project official: one row per ``Agent``.
CATALOG_ROW_KEYS: frozenset[str] = frozenset(
    {
        "group",
        "name",
        "slug",
        "uuid",
        "about",
        "assigned",
        "active",
        "is_official",
        "category",
        "systems",
        "mcps",
        "conversation_example",
    }
)

# Backward-compatible alias for tests/imports.
CATALOG_AGENT_ROW_KEYS = CATALOG_ROW_KEYS


def project_agent_assignment_map(
    project_uuid: str,
    *,
    include_inactive_integrated: bool,
) -> dict[int, tuple[bool, bool]]:
    """One DB round-trip: ``agent_id`` -> ``(assigned, active)`` for my-agents / official list rows.

    Semantics match ``build_row_from_project_agent`` when no preloaded map is passed.
    """
    rows = list(
        IntegratedAgent.objects.filter(project__uuid=project_uuid)
        .order_by("agent_id", "-is_active", "-id")
        .values_list("agent_id", "is_active")
    )
    result: dict[int, tuple[bool, bool]] = {}
    for agent_id, chunk in groupby(rows, key=lambda r: r[0]):
        flags = [r[1] for r in chunk]
        has_active = any(flags)
        has_any = bool(flags)
        assigned = has_any if include_inactive_integrated else has_active
        active = flags[0]
        result[agent_id] = (assigned, active)
    return result


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
    for system_slug in sorted(by_system.keys(), key=_system_bucket_sort_key):
        out.extend(by_system[system_slug])
    return _sort_mcps(out)


def _mcps_for_standalone_agent(agent: Agent) -> list[dict[str, Any]]:
    mcps = (
        agent.mcps.filter(is_active=True)
        .select_related("system")
        .prefetch_related("config_options", "credential_templates")
    )
    return _sort_mcps([_serialize_mcp(m) for m in mcps])


def _mcps_for_agent(agent: Agent, group_slug: str | None) -> list[dict[str, Any]]:
    if group_slug:
        return _flatten_group_mcps(group_slug)
    return _mcps_for_standalone_agent(agent)


def _catalog_systems_value(systems: list[str] | None, agent: Agent) -> list[str] | None:
    """Row-level ``systems``: ``null`` when there are no slugs (not ``[]`` or ``no_system``)."""
    slugs = systems if systems is not None else [s.slug for s in agent.systems.all()]
    return slugs if slugs else None


def _build_catalog_row(
    agent: Agent,
    *,
    assigned: bool,
    active: bool | None,
    systems: list[str] | None = None,
    mcps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Single novo retorno row (group view on v1 official, agent view on my-agents / team)."""
    group = getattr(agent, "group", None)
    group_slug = group.slug if group else None
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
        "systems": _catalog_systems_value(systems, agent),
        "mcps": mcps if mcps is not None else _mcps_for_agent(agent, group_slug),
        "conversation_example": _conversation_example_payload(agent),
    }


def build_row_from_integrated(integrated: IntegratedAgent) -> dict[str, Any]:
    """Team roster row — same novo retorno as my-agents / official project list."""
    agent = integrated.agent
    project_uuid = str(integrated.project.uuid) if integrated.project_id else None
    row = build_row_from_project_agent(agent, project_uuid, include_inactive_integrated=False)
    row["assigned"] = True
    row["active"] = integrated.is_active
    return row


def build_row_from_project_agent(
    agent: Agent,
    project_uuid: str | None,
    *,
    include_inactive_integrated: bool = False,
    assignment_by_agent_id: dict[int, tuple[bool, bool]] | None = None,
) -> dict[str, Any]:
    """Catalog row for one ``Agent`` (my-agents, project official list, team).

    Pass ``assignment_by_agent_id`` from ``project_agent_assignment_map`` when building many rows
    for the same project to avoid N+1 queries on ``IntegratedAgent``.
    """
    assigned = False
    active: bool | None = None
    if project_uuid:
        if assignment_by_agent_id is not None:
            assigned, active = assignment_by_agent_id.get(agent.pk, (False, False))
        else:
            qs_all = IntegratedAgent.objects.filter(project__uuid=project_uuid, agent=agent)
            qs_active = qs_all.filter(is_active=True)
            if include_inactive_integrated:
                assigned = qs_all.exists()
            else:
                assigned = qs_active.exists()
            integrated = qs_all.order_by("-is_active", "-id").first()
            active = integrated.is_active if integrated else False

    return _build_catalog_row(agent, assigned=assigned, active=active)


def _integrated_assignment_flags(project_uuid: str | None, agent_uuids: list) -> tuple[bool, bool | None]:
    """``assigned`` = any active IA; ``active`` reflects integration state for the group."""
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


def build_official_group_row(
    group_agents: list[Agent],
    group_slug: str,
    project_uuid: str | None,
) -> dict[str, Any]:
    """One catalog row per official ``AgentGroup`` (same field set as per-agent rows, no nested ``agents``)."""
    group_agents = sorted(group_agents, key=lambda a: (a.name, str(a.uuid)))
    base = group_agents[0]
    systems_sorted = _sort_systems(get_all_systems_for_group(group_slug))
    agent_uuids = [a.uuid for a in group_agents]
    assigned, active = _integrated_assignment_flags(project_uuid, agent_uuids)
    return _build_catalog_row(
        base,
        assigned=assigned,
        active=active,
        systems=systems_sorted,
        mcps=_flatten_group_mcps(group_slug),
    )
