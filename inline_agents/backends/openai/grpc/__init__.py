"""
gRPC Client for streaming messages to external services.
"""

from inline_agents.backends.openai.grpc.streaming_client import (
    MessageStreamingClient,
    is_grpc_enabled,
)

__all__ = ["MessageStreamingClient", "is_grpc_enabled"]
