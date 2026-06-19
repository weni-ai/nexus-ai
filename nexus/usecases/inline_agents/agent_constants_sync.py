from __future__ import annotations

from typing import Any

from django.db import transaction

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
    if not row.agents.filter(pk=agent.pk).exists():
        row.agents.add(agent)


@transaction.atomic
def sync_agent_constants_from_payload(
    agent: Agent,
    project: Project,
    constants: dict[str, Any],
    *,
    prune_missing: bool = False,
) -> None:
    """Create or update AgentConstant rows from a weni-cli push payload."""
    linked_to_agent = {
        row.key: row for row in AgentConstant.objects.filter(project=project, agents=agent).select_for_update()
    }
    payload_keys: set[str] = set()

    for key, constant_def in constants.items():
        if not isinstance(constant_def, dict):
            continue
        payload_keys.add(key)
        fields = fields_from_yaml_constant(key, constant_def)
        row = linked_to_agent.get(key) or AgentConstant.objects.filter(project=project, key=key).first()
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
        linked_to_agent[key] = row

    if not prune_missing:
        return

    for key, row in linked_to_agent.items():
        if key in payload_keys:
            continue
        if row.agents.count() == 1:
            row.delete()
        else:
            row.agents.remove(agent)
