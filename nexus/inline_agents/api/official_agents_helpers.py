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
        "description_en": mcp.description_en,
        "description_es": mcp.description_es,
        "description_pt": mcp.description_pt,
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
    """Unique system slugs for a group from its MCPs."""
    systems = list(
        AgentSystem.objects.filter(mcps__groups__slug=group_slug, mcps__is_active=True)
        .values_list("slug", flat=True)
        .distinct()
    )

    has_no_system_mcps = MCP.objects.filter(groups__slug=group_slug, is_active=True, system__isnull=True).exists()

    if has_no_system_mcps:
        systems.append("no_system")

    return _sort_systems(systems)


def get_all_mcps_for_group(group_slug: str) -> dict:
    """All MCPs for a group keyed by system slug."""
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
        system_slug = mcp.system.slug if mcp.system else "no_system"
        if system_slug not in result:
            result[system_slug] = []

        result[system_slug].append(_serialize_mcp(mcp))

    for system_slug in result:
        result[system_slug] = _sort_mcps(result[system_slug])

    return result
