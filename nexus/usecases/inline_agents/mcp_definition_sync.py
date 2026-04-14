from __future__ import annotations

from typing import Any

from nexus.inline_agents.models import MCP, MCPConfigOption, MCPCredentialTemplate

_TYPE_MAP = {
    "text": MCPConfigOption.TEXT,
    "number": MCPConfigOption.NUMBER,
    "checkbox": MCPConfigOption.CHECKBOX,
    "select": MCPConfigOption.SELECT,
    "radio": MCPConfigOption.RADIO,
    "switch": MCPConfigOption.SWITCH,
}


def _mcp_constant_type(raw: Any) -> str:
    if not isinstance(raw, str):
        return MCPConfigOption.TEXT
    return _TYPE_MAP.get(raw.strip().lower(), MCPConfigOption.TEXT)


def _normalize_select_options(options: Any) -> list[dict[str, Any]]:
    if not isinstance(options, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in options:
        if not isinstance(item, dict):
            continue
        name = item.get("name") if item.get("name") is not None else item.get("label")
        val = item.get("value")
        if name is not None and val is not None:
            normalized.append({"name": str(name), "value": val})
    return normalized


def _upsert_credential_template(mcp: MCP, key: str, cred_data: dict[str, Any]) -> None:
    """Create or partially update a credential template (only keys present in cred_data)."""
    existing = MCPCredentialTemplate.objects.filter(mcp=mcp, name=key).first()
    if existing:
        fields: list[str] = []
        if "label" in cred_data:
            existing.label = str(cred_data["label"])[:255]
            fields.append("label")
        if "placeholder" in cred_data:
            existing.placeholder = str(cred_data.get("placeholder") or "")[:255]
            fields.append("placeholder")
        if "is_confidential" in cred_data:
            existing.is_confidential = bool(cred_data["is_confidential"])
            fields.append("is_confidential")
        if fields:
            existing.save(update_fields=fields)
        return

    MCPCredentialTemplate.objects.create(
        mcp=mcp,
        name=key,
        label=str(cred_data.get("label", key))[:255],
        placeholder=str(cred_data.get("placeholder") or "")[:255],
        is_confidential=cred_data.get("is_confidential", True),
    )


def _apply_scalar_config_option(mcp: MCP, name: str, value: Any, existing: MCPConfigOption | None) -> None:
    if existing:
        MCPConfigOption.objects.filter(pk=existing.pk).update(default_value=value)
        return
    MCPConfigOption.objects.create(
        mcp=mcp,
        name=name,
        label=str(name)[:255],
        type=MCPConfigOption.TEXT,
        options=[],
        is_required=False,
        default_value=value,
    )


def _config_option_updates_from_dict(value: dict[str, Any], existing: MCPConfigOption | None) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if "label" in value and isinstance(value["label"], str):
        updates["label"] = value["label"][:255]

    if "type" in value:
        updates["type"] = _mcp_constant_type(value["type"])

    merged_type = updates.get("type") or (existing.type if existing else MCPConfigOption.TEXT)

    if "options" in value:
        if merged_type in (MCPConfigOption.RADIO, MCPConfigOption.SELECT):
            updates["options"] = _normalize_select_options(value["options"])
        else:
            updates["options"] = []

    if "default" in value:
        updates["default_value"] = value["default"]

    if "required" in value:
        updates["is_required"] = bool(value["required"])

    if "type" in value and updates["type"] not in (MCPConfigOption.RADIO, MCPConfigOption.SELECT):
        updates["options"] = []

    return updates


def _apply_dict_config_option(mcp: MCP, name: str, value: dict[str, Any], existing: MCPConfigOption | None) -> None:
    updates = _config_option_updates_from_dict(value, existing)
    if existing:
        if not updates:
            return
        for field, val in updates.items():
            setattr(existing, field, val)
        existing.save()
        return

    if not updates:
        return

    MCPConfigOption.objects.create(
        mcp=mcp,
        name=name,
        label=updates.get("label", str(name)[:255]),
        type=updates.get("type", MCPConfigOption.TEXT),
        options=updates.get("options", []),
        is_required=updates.get("is_required", False),
        default_value=updates.get("default_value"),
    )


def _upsert_mcp_config_option_from_constant(mcp: MCP, name: str, value: Any) -> None:
    """Create or partially update a config option.

    - Scalar value: existing rows only get ``default_value`` updated (type/label/options preserved).
    - Dict value: only keys present in the dict are applied; omitting ``default`` leaves ``default_value`` unchanged.
    """
    existing = MCPConfigOption.objects.filter(mcp=mcp, name=name).first()
    if not isinstance(value, dict):
        _apply_scalar_config_option(mcp, name, value, existing)
        return
    _apply_dict_config_option(mcp, name, value, existing)


def sync_mcp_templates_from_agent_payload(
    mcp: MCP,
    credentials: dict[str, Any] | None,
    constants: dict[str, Any] | None,
) -> None:
    """Create or update MCPCredentialTemplate / MCPConfigOption rows for this MCP."""
    if credentials:
        for key, cred_data in credentials.items():
            if isinstance(cred_data, dict):
                _upsert_credential_template(mcp, key, cred_data)

    if constants:
        for key, value in constants.items():
            _upsert_mcp_config_option_from_constant(mcp, key, value)
