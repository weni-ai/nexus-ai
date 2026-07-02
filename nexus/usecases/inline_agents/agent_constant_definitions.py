from __future__ import annotations

from typing import Any

from nexus.inline_agents.models import AgentConstant

_TYPE_MAP = {
    "text": AgentConstant.TEXT,
    "number": AgentConstant.NUMBER,
    "checkbox": AgentConstant.CHECKBOX,
    "select": AgentConstant.SELECT,
    "radio": AgentConstant.RADIO,
    "switch": AgentConstant.SWITCH,
}


def constant_type_from_yaml(raw: Any) -> str:
    if not isinstance(raw, str):
        return AgentConstant.TEXT
    return _TYPE_MAP.get(raw.strip().lower(), AgentConstant.TEXT)


def normalize_constant_options(constant_def: dict[str, Any], field_type: str) -> list[dict[str, Any]]:
    if field_type not in (AgentConstant.RADIO, AgentConstant.SELECT):
        return []
    options = constant_def.get("options")
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


def fields_from_yaml_constant(key: str, constant_def: dict[str, Any]) -> dict[str, Any]:
    field_type = constant_type_from_yaml(constant_def.get("type"))
    return {
        "key": key,
        "label": str(constant_def.get("label", key))[:255],
        "type": field_type,
        "options": normalize_constant_options(constant_def, field_type),
        "default_value": constant_def.get("default"),
        "is_required": bool(constant_def.get("required", False)),
        "definition": constant_def,
    }


def serialize_agent_constant_for_api(constant: AgentConstant) -> dict[str, Any]:
    options = constant.options
    if constant.type in (AgentConstant.SWITCH, AgentConstant.NUMBER, AgentConstant.TEXT, AgentConstant.CHECKBOX):
        if not isinstance(options, list):
            options = []
    payload: dict[str, Any] = {
        "name": constant.key,
        "label": constant.label,
        "type": constant.type,
        "options": options,
        "is_required": constant.is_required,
    }
    if constant.default_value is not None:
        payload["default_value"] = constant.default_value
    return payload
