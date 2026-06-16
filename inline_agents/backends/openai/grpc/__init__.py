"""
gRPC Client for streaming messages to external services.
"""

from inline_agents.backends.openai.grpc.completion import deliver_final_grpc_stream
from inline_agents.backends.openai.grpc.streaming_client import (
    MessageStreamingClient,
    StreamingSession,
    is_grpc_enabled,
)

__all__ = [
    "MessageStreamingClient",
    "StreamingSession",
    "deliver_final_grpc_stream",
    "is_grpc_enabled",
]
