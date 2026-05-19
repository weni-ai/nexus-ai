"""Read-time shaping of inline trace payloads for API responses only (storage unchanged)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.db.models import Q

logger = logging.getLogger(__name__)

MANAGER_TRACE_AGENT_NAME = "manager"


def remap_inline_traces_config_agent_names(traces: list[Any], *, project_uuid: str | None) -> list[Any]:
    """Replace ``trace.config.agentName`` (collaborator id / slug) with the same list label as catalog/team APIs."""
    if not traces or not project_uuid:
        return traces
    if not _is_valid_uuid_string(project_uuid):
        return traces
    try:
        identifiers = _collect_config_agent_names(traces)
        if not identifiers:
            return traces
        display_by_slug, display_ci = _load_display_names_by_slug(project_uuid, identifiers)
        if not display_by_slug and not display_ci:
            return traces
        for item in traces:
            _remap_one_item(item, display_by_slug, display_ci)
        return traces
    except Exception:
        logger.exception(
            "inline trace agentName remap skipped (returning raw traces)",
            extra={"project_uuid": project_uuid},
        )
        return traces


def _is_valid_uuid_string(value: str) -> bool:
    s = value.strip()
    if not s:
        return False
    try:
        uuid.UUID(s)
    except ValueError:
        return False
    return True


def _collect_config_agent_names(traces: list[Any]) -> set[str]:
    out: set[str] = set()
    for item in traces:
        cfg = _item_trace_config(item)
        if not cfg:
            continue
        name = cfg.get("agentName")
        if isinstance(name, str) and name.strip():
            out.add(name.strip())
    return out


def _item_trace_config(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    outer = item.get("trace")
    if not isinstance(outer, dict):
        return None
    cfg = outer.get("config")
    return cfg if isinstance(cfg, dict) else None


def _slug_iexact_or_q(lookup: str, tokens: set[str]) -> Q:
    """OR of ``lookup__iexact`` for each token (trace casing may differ from DB slug casing)."""
    if not tokens:
        return Q(pk__in=[])
    q = Q()
    for t in tokens:
        if not t:
            continue
        q |= Q(**{f"{lookup}__iexact": t})
    return q


def _load_display_names_by_slug(project_uuid: str, identifiers: set[str]) -> tuple[dict[str, str], dict[str, str]]:
    from nexus.inline_agents.api.serializers import inline_agent_list_display_name
    from nexus.inline_agents.models import Agent as InlineAgent
    from nexus.inline_agents.models import IntegratedAgent

    wanted = {i for i in identifiers if i.lower() != MANAGER_TRACE_AGENT_NAME}
    if not wanted:
        return {}, {}

    owned = (
        InlineAgent.objects.filter(project__uuid=project_uuid)
        .filter(_slug_iexact_or_q("slug", wanted))
        .select_related("group", "group__modal")
    )
    int_ids = list(
        IntegratedAgent.objects.filter(project__uuid=project_uuid)
        .filter(_slug_iexact_or_q("agent__slug", wanted))
        .values_list("agent_id", flat=True)
    )
    integrated_qs = (
        InlineAgent.objects.filter(pk__in=int_ids).select_related("group", "group__modal")
        if int_ids
        else InlineAgent.objects.none()
    )

    display_by_slug: dict[str, str] = {}
    display_ci: dict[str, str] = {}
    for ag in list(owned) + list(integrated_qs):
        label = inline_agent_list_display_name(ag)
        display_by_slug[ag.slug] = label
        display_ci[ag.slug.lower()] = label
    return display_by_slug, display_ci


def _remap_one_item(item: Any, display_by_slug: dict[str, str], display_ci: dict[str, str]) -> None:
    cfg = _item_trace_config(item)
    if not cfg:
        return
    name = cfg.get("agentName")
    if not isinstance(name, str) or not name.strip():
        return
    stripped = name.strip()
    if stripped.lower() == MANAGER_TRACE_AGENT_NAME:
        return
    new = display_by_slug.get(stripped) or display_ci.get(stripped.lower())
    if new:
        cfg["agentName"] = new
