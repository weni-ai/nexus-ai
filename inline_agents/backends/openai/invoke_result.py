import ast
import json
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass(frozen=True)
class SkipDirectBroadcastResult:
    """
    Final output when a tool returned is_final_output with messages already
    delivered (e.g. Lambda). Production dispatch must not re-broadcast;
    preview may still dispatch so the simulator shows the payload.
    """

    messages: List[Any]


def _coerce_tool_output_value(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            try:
                return ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                pass
    return raw


def parse_skip_direct_from_tool_output(raw: Any) -> Optional[SkipDirectBroadcastResult]:
    if isinstance(raw, SkipDirectBroadcastResult):
        return raw
    if getattr(raw, "__class__", type(None)).__name__ == "SkipDirectBroadcastResult" and hasattr(raw, "messages"):
        return SkipDirectBroadcastResult(messages=getattr(raw, "messages", []))
    parsed = _coerce_tool_output_value(raw)
    if isinstance(parsed, dict) and parsed.get("is_final_output"):
        messages = parsed.get("messages")
        if messages is not None:
            return SkipDirectBroadcastResult(messages=messages)
    return None
