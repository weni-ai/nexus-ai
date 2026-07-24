import logging
from typing import Any, Optional, Protocol
from uuid import uuid4

import pendulum

logger = logging.getLogger(__name__)

CONTEXT_DELIMITER = "; Context:"
DEFAULT_CONTEXT_TOOL_NAME = "get_context"
DEFAULT_AGENT_NAME = "manager"


class SessionLike(Protocol):
    async def add_items(self, items: list) -> None: ...


class TraceHandlerLike(Protocol):
    async def send_trace(
        self,
        context_data: Any,
        agent_name: str,
        trace_type: str,
        trace_data: Optional[dict] = None,
        tool_name: str = "",
    ) -> None: ...


def extract_message_context(text: str) -> tuple[str, Optional[str]]:
    """Split user text and optional `; Context:` suffix.

    Returns:
        (clean_user_text, context) where context is None when the delimiter is absent.
    """
    if not text or CONTEXT_DELIMITER not in text:
        return text, None

    user_text, context = text.split(CONTEXT_DELIMITER, 1)
    return user_text.strip(), context.strip() or None


async def inject_context_as_tool_result(
    session: SessionLike,
    context: str,
    tool_name: str = DEFAULT_CONTEXT_TOOL_NAME,
) -> None:
    """Persist context in session history as a paired function_call + function_call_output."""
    call_id = f"call_ctx_{uuid4().hex}"
    await session.add_items(
        [
            {
                "type": "function_call",
                "call_id": call_id,
                "name": tool_name,
                "arguments": "{}",
            },
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": context,
            },
        ]
    )
    logger.info("Injected context as tool result into session tool_name=%s call_id=%s", tool_name, call_id)


async def emit_context_tool_traces(
    trace_handler: TraceHandlerLike,
    context_data: Any,
    context: str,
    tool_name: str = DEFAULT_CONTEXT_TOOL_NAME,
    agent_name: str = DEFAULT_AGENT_NAME,
) -> None:
    """Emit executing_tool + tool_result_received traces (S3 buffer + preview websocket)."""
    session_id = context_data.session.get_session_id()
    event_time = pendulum.now().to_iso8601_string()

    executing_trace = {
        "collaboratorName": agent_name,
        "eventTime": event_time,
        "sessionId": session_id,
        "trace": {
            "orchestrationTrace": {
                "invocationInput": {
                    "actionGroupInvocationInput": {
                        "actionGroupName": tool_name,
                        "executionType": "LAMBDA",
                        "function": tool_name,
                        "parameters": [],
                    },
                }
            }
        },
    }
    await trace_handler.send_trace(context_data, agent_name, "executing_tool", executing_trace, tool_name=tool_name)

    result_trace = {
        "collaboratorName": agent_name,
        "eventTime": pendulum.now().to_iso8601_string(),
        "sessionId": session_id,
        "trace": {
            "orchestrationTrace": {
                "observation": {
                    "actionGroupInvocationOutput": {
                        "text": context,
                        "tool_name": tool_name,
                        "parameters": [],
                    },
                }
            }
        },
    }
    await trace_handler.send_trace(context_data, agent_name, "tool_result_received", result_trace, tool_name=tool_name)
    logger.info("Emitted context tool traces tool_name=%s agent_name=%s", tool_name, agent_name)
