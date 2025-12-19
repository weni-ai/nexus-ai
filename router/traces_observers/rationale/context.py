"""
Context objects for RationaleObserver to reduce parameter passing complexity.
"""

from dataclasses import dataclass
from typing import Callable, Dict, Optional


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
    message_external_id: str
    user_email: Optional[str]

    @classmethod
    def from_kwargs(cls, **kwargs) -> "RationaleContext":
        """Create RationaleContext from perform method kwargs."""
        return cls(
            session_id=kwargs.get("session_id", ""),
            user_input=kwargs.get("user_input", ""),
            contact_urn=kwargs.get("contact_urn", ""),
            project_uuid=kwargs.get("project_uuid", ""),
            contact_name=kwargs.get("contact_name", ""),
            channel_uuid=kwargs.get("channel_uuid"),
            send_message_callback=kwargs.get("send_message_callback"),
            preview=kwargs.get("preview", False),
            message_external_id=kwargs.get("message_external_id", ""),
            user_email=kwargs.get("user_email"),
        )


@dataclass
class TraceData:
    """Helper class for accessing trace data safely."""

    inline_traces: Dict

    def get_rationale_text(self) -> Optional[str]:
        """Extract rationale text from trace data."""
        try:
            trace = self.inline_traces.get("trace", {})
            orchestration = trace.get("orchestrationTrace", {})
            rationale = orchestration.get("rationale", {})
            return rationale.get("text")
        except (AttributeError, KeyError, TypeError):
            return None

    def has_called_agent(self) -> bool:
        """Check if trace indicates an agent was called."""
        try:
            trace = self.inline_traces.get("trace", {})
            orchestration = trace.get("orchestrationTrace", {})
            invocation = orchestration.get("invocationInput", {})
            return "agentCollaboratorInvocationInput" in invocation
        except (AttributeError, KeyError, TypeError):
            return False

    def is_valid(self) -> bool:
        """Check if trace data is valid."""
        return self.inline_traces is not None and "trace" in self.inline_traces
