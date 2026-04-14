"""Apply agent-definition credentials/constants to MCP templates (CLI push / YAML)."""

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


def _scalar_default(value: Any) -> Any:
    if isinstance(value, dict):
        if "default" in value:
            return value["default"]
        return None
    return value


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


def _config_option_defaults(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "default_value": value,
            "label": str(name)[:255],
            "type": MCPConfigOption.TEXT,
            "options": [],
            "is_required": False,
        }

    opt_type = _mcp_constant_type(value.get("type"))
    raw_options = value.get("options") or []
    if opt_type in (MCPConfigOption.RADIO, MCPConfigOption.SELECT):
        options_payload = _normalize_select_options(raw_options)
    else:
        options_payload = []

    label_raw = value.get("label")
    label = str(label_raw)[:255] if isinstance(label_raw, str) else str(name)[:255]

    return {
        "default_value": _scalar_default(value),
        "label": label,
        "type": opt_type,
        "options": options_payload,
        "is_required": bool(value.get("required", False)),
    }


def sync_mcp_templates_from_agent_payload(
    mcp: MCP,
    credentials: dict[str, Any] | None,
    constants: dict[str, Any] | None,
) -> None:
    """Create or update MCPCredentialTemplate / MCPConfigOption rows for this MCP."""
    if credentials:
        for key, cred_data in credentials.items():
            if isinstance(cred_data, dict):
                MCPCredentialTemplate.objects.update_or_create(
                    mcp=mcp,
                    name=key,
                    defaults={
                        "label": str(cred_data.get("label", key))[:255],
                        "placeholder": str(cred_data.get("placeholder") or "")[:255],
                        "is_confidential": cred_data.get("is_confidential", True),
                    },
                )

    if constants:
        for key, value in constants.items():
            defaults = _config_option_defaults(key, value)
            MCPConfigOption.objects.update_or_create(
                mcp=mcp,
                name=key,
                defaults=defaults,
            )
