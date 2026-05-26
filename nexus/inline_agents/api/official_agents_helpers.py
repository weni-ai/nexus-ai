"""Official-agent MCP/system helpers shared by views and serializers (avoids circular imports)."""

from nexus.inline_agents.models import MCP, Agent, AgentGroup, AgentSystem


def _sort_mcps(mcps: list) -> list:
    """Sort MCPs so that 'Default' appears first, then alphabetical order."""
    if not isinstance(mcps, list):
        return mcps

    def sort_key(mcp):
        name = mcp.get("name", "") if isinstance(mcp, dict) else ""
        is_default = name.lower() == "default"
        return (0 if is_default else 1, name.lower())

    return sorted(mcps, key=sort_key)


def _serialize_mcp(mcp) -> dict:
    """Serialize MCP with config and credentials."""
    mcp_data = {
        "name": mcp.name,
        "description": {
            "en": mcp.description_en,
            "pt": mcp.description_pt,
            "es": mcp.description_es,
        },
        "system": mcp.system.slug if mcp.system else None,
        "config": [],
        "credentials": [],
    }

    for config_option in mcp.config_options.all():
        options = config_option.options
        if config_option.type in ["SWITCH", "NUMBER", "TEXT", "CHECKBOX"]:
            if not isinstance(options, list):
                options = []

        config_item = {
            "name": config_option.name,
            "label": config_option.label,
            "type": config_option.type,
            "options": options,
            "is_required": config_option.is_required,
        }
        if config_option.default_value is not None:
            config_item["default_value"] = config_option.default_value
        mcp_data["config"].append(config_item)

    for template in mcp.credential_templates.all():
        mcp_data["credentials"].append(
            {
                "name": template.name,
                "label": template.label,
                "placeholder": template.placeholder,
                "is_confidential": template.is_confidential,
            }
        )

    return mcp_data


def _mcp_nested_prefetch_ready(mcp: MCP) -> bool:
    """True when config_options and credential_templates were prefetched on this MCP instance."""
    cache = getattr(mcp, "_prefetched_objects_cache", None)
    if not isinstance(cache, dict):
        return False
    return "config_options" in cache and "credential_templates" in cache


def aggregate_mcp_definitions_for_agent(agent: Agent) -> dict:
    """
    Merge MCP config options (constants) and credential templates for all active MCPs on an agent.

    Used by inline AgentSerializer (e.g. my-agents) so clients receive the same MCP shape as official
    helpers, with deduplication by field name across MCPs.
    """
    config_items: list = []
    credential_items: list = []
    seen_config: set[str] = set()
    seen_cred: set[str] = set()

    cached_mcps = getattr(agent, "_prefetched_objects_cache", {}).get("mcps")
    if cached_mcps is not None:
        active = [m for m in cached_mcps if m.is_active]
        if not active:
            mcp_iter = []
        elif all(_mcp_nested_prefetch_ready(m) for m in active):
            mcp_iter = active
        else:
            # Parent prefetched mcps without nested relations — one query with full prefetch
            mcp_iter = (
                MCP.objects.filter(pk__in=[m.pk for m in active], is_active=True)
                .select_related("system")
                .prefetch_related("config_options", "credential_templates")
                .order_by("order", "name")
            )
    else:
        mcp_iter = (
            agent.mcps.filter(is_active=True)
            .select_related("system")
            .prefetch_related("config_options", "credential_templates")
            .order_by("order", "name")
        )

    for mcp in mcp_iter:
        data = _serialize_mcp(mcp)
        for c in data["config"]:
            name = c.get("name")
            if name and name not in seen_config:
                seen_config.add(name)
                config_items.append(c)
        for t in data["credentials"]:
            name = t.get("name")
            if name and name not in seen_cred:
                seen_cred.add(name)
                credential_items.append(t)

    return {"config": config_items, "credentials": credential_items}


def get_mcps_for_agent_system(agent_slug: str, system_slug: str) -> list:
    """MCPs for an agent/system combination from database models."""
    agent = Agent.objects.filter(slug=agent_slug, is_official=True).first()
    system = AgentSystem.objects.filter(slug__iexact=system_slug).first()

    if not agent or not system:
        return []

    mcps = (
        agent.mcps.filter(system=system, is_active=True)
        .select_related("system")
        .prefetch_related("config_options", "credential_templates")
    )

    result = [_serialize_mcp(mcp) for mcp in mcps]
    return _sort_mcps(result)


def _sort_systems(systems: list) -> list:
    """Sort systems with 'vtex' first, then alphabetical."""
    sorted_systems = sorted(systems)
    if "vtex" in sorted_systems:
        sorted_systems.remove("vtex")
        sorted_systems.insert(0, "vtex")
    return sorted_systems


def get_all_systems_for_group(group_slug: str) -> list:
    """Unique AgentSystem slugs for a group (MCPs without system do not add a synthetic slug)."""
    systems = list(
        AgentSystem.objects.filter(mcps__groups__slug=group_slug, mcps__is_active=True)
        .values_list("slug", flat=True)
        .distinct()
    )
    return _sort_systems(systems)


def _system_bucket_sort_key(slug: str | None) -> tuple:
    """Sort order for MCP buckets: vtex first, then named systems, then unscoped (``None``)."""
    if slug is None:
        return (2, "")
    normalized = str(slug).lower()
    return (0 if normalized == "vtex" else 1, normalized)


def group_mcps_for_system(all_group_mcps: dict, system: str | None) -> list:
    """MCP payloads for ``system``; empty/None selects MCPs whose ``system`` field is null."""
    if not system:
        return all_group_mcps.get(None, [])
    system_lower = system.lower()
    for sys_key, sys_mcps in all_group_mcps.items():
        if sys_key is not None and sys_key.lower() == system_lower:
            return sys_mcps
    return []


def get_all_mcps_for_group(group_slug: str) -> dict:
    """All MCPs for a group keyed by system slug (``None`` when MCP has no AgentSystem)."""
    try:
        group = AgentGroup.objects.get(slug=group_slug)
    except AgentGroup.DoesNotExist:
        return {}

    mcps = (
        group.mcps.filter(is_active=True)
        .select_related("system")
        .prefetch_related("config_options", "credential_templates")
    )

    result = {}
    for mcp in mcps:
        system_slug = mcp.system.slug if mcp.system else None
        if system_slug not in result:
            result[system_slug] = []

        result[system_slug].append(_serialize_mcp(mcp))

    for system_slug in result:
        result[system_slug] = _sort_mcps(result[system_slug])

    return result
