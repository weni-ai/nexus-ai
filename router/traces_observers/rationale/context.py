"""
Context objects for RationaleObserver to reduce parameter passing complexity.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class RationaleContext:
    """Context object containing all parameters needed for rationale processing."""

    session_id: str
    user_input: str
    contact_urn: str
    project_uuid: str
    contact_name: str
    channel_uuid: Optional[str]
    send_message_callback: Optional[Callable]
    preview: bool
    preview_websocket: bool
    message_external_id: str
    user_email: Optional[str]

    @classmethod
    def from_kwargs(cls, **kwargs) -> "RationaleContext":
        """Create RationaleContext from perform method kwargs."""
        message_external_id = kwargs.get("message_external_id") or kwargs.get("msg_external_id") or ""
        return cls(
            session_id=kwargs.get("session_id", ""),
            user_input=kwargs.get("user_input", ""),
            contact_urn=kwargs.get("contact_urn", ""),
            project_uuid=kwargs.get("project_uuid", ""),
            contact_name=kwargs.get("contact_name", ""),
            channel_uuid=kwargs.get("channel_uuid"),
            send_message_callback=kwargs.get("send_message_callback"),
            preview=kwargs.get("preview", False),
            preview_websocket=kwargs.get("preview_websocket", False),
            message_external_id=message_external_id,
            user_email=kwargs.get("user_email"),
        )


@dataclass
class TraceData:
    """Helper class for accessing trace data safely."""

    inline_traces: Dict

    def _orchestration_trace(self) -> Dict[str, Any]:
        """
        Resolve orchestrationTrace for Bedrock and OpenAI shapes.

        Bedrock / flat OpenAI agent traces:
          inline_traces["trace"]["orchestrationTrace"]

        OpenAI thinking/rationale traces wrap once more:
          inline_traces["trace"]["trace"]["orchestrationTrace"]
        """
        try:
            if not isinstance(self.inline_traces, dict):
                return {}
            trace = self.inline_traces.get("trace") or {}
            if not isinstance(trace, dict):
                return {}
            if "orchestrationTrace" in trace:
                orchestration = trace.get("orchestrationTrace") or {}
                return orchestration if isinstance(orchestration, dict) else {}
            nested = trace.get("trace") or {}
            if isinstance(nested, dict) and "orchestrationTrace" in nested:
                orchestration = nested.get("orchestrationTrace") or {}
                return orchestration if isinstance(orchestration, dict) else {}
            return {}
        except (AttributeError, KeyError, TypeError):
            return {}

    def get_rationale_text(self) -> Optional[str]:
        """Extract rationale text from trace data."""
        try:
            rationale = self._orchestration_trace().get("rationale") or {}
            if not isinstance(rationale, dict):
                return None
            text = rationale.get("text")
            return text if text else None
        except (AttributeError, KeyError, TypeError):
            return None

    def has_called_agent(self) -> bool:
        """Check if trace indicates an agent was called."""
        try:
            invocation = self._orchestration_trace().get("invocationInput") or {}
            if not isinstance(invocation, dict):
                return False
            return "agentCollaboratorInvocationInput" in invocation
        except (AttributeError, KeyError, TypeError):
            return False

    def is_valid(self) -> bool:
        """Check if trace data is valid."""
        return self.inline_traces is not None and "trace" in self.inline_traces
