from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Count, Q

from nexus.inline_agents.models import Agent, AgentConstant
from nexus.projects.models import Project
from nexus.usecases.inline_agents.agent_constant_definitions import fields_from_yaml_constant


def iter_agent_constant_defaults(agent: Agent) -> dict[str, Any]:
    """Default constant values for an agent, using prefetched rows when available."""
    cache = getattr(agent, "_prefetched_objects_cache", None)
    if isinstance(cache, dict) and "agentconstant_set" in cache:
        rows = cache["agentconstant_set"]
    else:
        rows = agent.agentconstant_set.all()
    return {row.key: row.default_value for row in rows if row.default_value is not None}


def _apply_constant_fields(row: AgentConstant, fields: dict[str, Any]) -> None:
    row.label = fields["label"]
    row.type = fields["type"]
    row.options = fields["options"]
    row.default_value = fields["default_value"]
    row.is_required = fields["is_required"]
    row.definition = fields["definition"]


def _link_agent_to_constant(agent: Agent, row: AgentConstant) -> None:
    agent_ids = {linked.pk for linked in row.agents.all()}
    if agent.pk not in agent_ids:
        row.agents.add(agent)


def _locked_constants_for_sync(
    project: Project,
    agent: Agent,
    payload_keys: set[str],
) -> dict[str, AgentConstant]:
    lock_filter = Q(agents=agent)
    if payload_keys:
        lock_filter |= Q(key__in=payload_keys)

    rows = (
        AgentConstant.objects.filter(project=project)
        .filter(lock_filter)
        .annotate(agent_count=Count("agents", distinct=True))
        .prefetch_related("agents")
        .order_by("key")
        .select_for_update()
    )
    locked_by_key: dict[str, AgentConstant] = {}
    for row in rows:
        locked_by_key.setdefault(row.key, row)
    return locked_by_key


def _linked_constants_for_agent(
    locked_by_key: dict[str, AgentConstant],
    agent: Agent,
) -> dict[str, AgentConstant]:
    return {key: row for key, row in locked_by_key.items() if any(linked.pk == agent.pk for linked in row.agents.all())}


@transaction.atomic
def sync_agent_constants_from_payload(
    agent: Agent,
    project: Project,
    constants: dict[str, Any],
    *,
    prune_missing: bool = False,
) -> None:
    """Create or update AgentConstant rows from a weni-cli push payload."""
    parsed: dict[str, dict[str, Any]] = {}
    for key, constant_def in constants.items():
        if isinstance(constant_def, dict):
            parsed[key] = fields_from_yaml_constant(key, constant_def)

    payload_keys = set(parsed.keys())
    locked_by_key = _locked_constants_for_sync(project, agent, payload_keys)
    linked_to_agent = _linked_constants_for_agent(locked_by_key, agent)

    for key, fields in parsed.items():
        row = locked_by_key.get(key)
        if row:
            _apply_constant_fields(row, fields)
            row.save()
            _link_agent_to_constant(agent, row)
            linked_to_agent[key] = row
            continue

        row = AgentConstant.objects.create(
            project=project,
            key=fields["key"],
            label=fields["label"],
            type=fields["type"],
            options=fields["options"],
            default_value=fields["default_value"],
            is_required=fields["is_required"],
            definition=fields["definition"],
        )
        row.agents.add(agent)
        locked_by_key[key] = row
        linked_to_agent[key] = row

    if not prune_missing:
        return

    for key, row in linked_to_agent.items():
        if key in payload_keys:
            continue
        if row.agent_count == 1:
            row.delete()
        else:
            row.agents.remove(agent)
