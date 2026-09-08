from __future__ import annotations

from typing import Any

from django.db import transaction

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


def _create_credential_template(mcp: MCP, key: str, cred_data: dict[str, Any]) -> None:
    MCPCredentialTemplate.objects.create(
        mcp=mcp,
        name=key,
        label=str(cred_data.get("label", key))[:255],
        placeholder=str(cred_data.get("placeholder") or "")[:255],
        is_confidential=cred_data.get("is_confidential", True),
    )


def _fields_from_constant_dict(value: dict[str, Any]) -> dict[str, Any] | None:
    """Build create kwargs from a YAML constant dict. Returns None when there is nothing to persist."""
    fields: dict[str, Any] = {}
    if "label" in value and isinstance(value["label"], str):
        fields["label"] = value["label"][:255]

    if "type" in value:
        fields["type"] = _mcp_constant_type(value["type"])

    option_type = fields.get("type", MCPConfigOption.TEXT)

    if "options" in value:
        if option_type in (MCPConfigOption.RADIO, MCPConfigOption.SELECT):
            fields["options"] = _normalize_select_options(value["options"])
        else:
            fields["options"] = []

    if "default" in value:
        fields["default_value"] = value["default"]

    if "required" in value:
        fields["is_required"] = bool(value["required"])

    if "type" in value and fields["type"] not in (MCPConfigOption.RADIO, MCPConfigOption.SELECT):
        fields["options"] = []

    if not fields:
        return None
    return fields


def _create_mcp_config_option_from_constant(mcp: MCP, name: str, value: Any) -> None:
    if not isinstance(value, dict):
        MCPConfigOption.objects.create(
            mcp=mcp,
            name=name,
            label=str(name)[:255],
            type=MCPConfigOption.TEXT,
            options=[],
            is_required=False,
            default_value=value,
        )
        return

    fields = _fields_from_constant_dict(value)
    if not fields:
        return

    MCPConfigOption.objects.create(
        mcp=mcp,
        name=name,
        label=fields.get("label", str(name)[:255]),
        type=fields.get("type", MCPConfigOption.TEXT),
        options=fields.get("options", []),
        is_required=fields.get("is_required", False),
        default_value=fields.get("default_value"),
    )


@transaction.atomic
def sync_mcp_templates_from_agent_payload(
    mcp: MCP,
    credentials: dict[str, Any] | None,
    constants: dict[str, Any] | None,
) -> None:
    """Replace MCPCredentialTemplate / MCPConfigOption rows for this MCP with the payload.

    Always clears both tables first, then recreates from ``credentials`` / ``constants``.
    A missing or empty section leaves that table empty.
    """
    MCPCredentialTemplate.objects.filter(mcp=mcp).delete()
    MCPConfigOption.objects.filter(mcp=mcp).delete()

    if credentials:
        for key, cred_data in credentials.items():
            if isinstance(cred_data, dict):
                _create_credential_template(mcp, key, cred_data)

    if constants:
        for key, value in constants.items():
            _create_mcp_config_option_from_constant(mcp, key, value)
