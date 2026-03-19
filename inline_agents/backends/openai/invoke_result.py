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
    """
    Única fonte de verdade para: tool devolveu encerramento direto (Lambda / is_final_output).
    Usado pelo `tool_use_behavior` do colaborador e do supervisor e pelo proxy colaborador→manager.
    """
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


def collaborator_run_output_for_manager(sub_run_final: Any) -> Any:
    """
    Resultado do `Runner.run` do colaborador → payload que o manager trata no mesmo `custom_tool_handler`
    (`is_final_output` + `messages`), ou o valor original se não for final.
    """
    skip = parse_skip_direct_from_tool_output(sub_run_final)
    if skip is not None:
        return {"is_final_output": True, "messages": skip.messages}
    return sub_run_final
