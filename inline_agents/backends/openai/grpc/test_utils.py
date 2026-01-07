"""
Test utilities for gRPC client.

Provides mock client and helpers for testing without a real gRPC server.
"""

from typing import Any, Dict, Iterator, List, Optional


class MockMessageStreamingClient:
    """
    Mock gRPC client for testing.

    Usage in tests:
        from inline_agents.backends.openai.grpc.test_utils import MockMessageStreamingClient

        def test_my_function(self):
            with patch('my_module.MessageStreamingClient', MockMessageStreamingClient):
                result = my_function()
                self.assertEqual(result['status'], 'success')
    """

    def __init__(self, *args, **kwargs):
        """Initialize mock client."""
        self.host = kwargs.get("host", "localhost")
        self.port = kwargs.get("port", 50051)
        self.connected = True
        self.calls = []  # Track all calls for assertions

    def check_connection(self, timeout: int = 5) -> bool:
        """Mock connection check - always returns True."""
        return self.connected

    def stream_messages_with_setup(
        self,
        msg_id: str,
        channel_uuid: str,
        contact_urn: str,
        messages: Optional[List[str]] = None,
        project_uuid: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Mock streaming - yields fake responses.

        You can customize responses by setting mock_responses attribute:
            mock_client = MockMessageStreamingClient()
            mock_client.mock_responses = [
                {'status': 'success', 'message': 'Custom response', 'is_final': True}
            ]
        """
        # Track the call
        self.calls.append(
            {
                "method": "stream_messages_with_setup",
                "msg_id": msg_id,
                "channel_uuid": channel_uuid,
                "contact_urn": contact_urn,
                "messages": messages,
            }
        )

        # Use custom responses if set, otherwise default
        if hasattr(self, "mock_responses"):
            responses = self.mock_responses
        else:
            # Default mock responses
            responses = [
                {
                    "status": "success",
                    "msg_id": msg_id,
                    "message": "Mock setup acknowledged",
                    "sequence": 0,
                    "is_final": False,
                    "error_code": None,
                    "error_message": None,
                    "data": {},
                },
            ]

            # Add response for each message
            if messages:
                for idx, msg in enumerate(messages):
                    responses.append(
                        {
                            "status": "success",
                            "msg_id": f"{msg_id}-content-{idx+1}",
                            "message": f"Mock response to: {msg[:50]}",
                            "sequence": idx + 1,
                            "is_final": False,
                            "error_code": None,
                            "error_message": None,
                            "data": {},
                        }
                    )

            # Final response
            responses.append(
                {
                    "status": "success",
                    "msg_id": msg_id,
                    "message": "Mock stream complete",
                    "sequence": len(responses),
                    "is_final": True,
                    "error_code": None,
                    "error_message": None,
                    "data": {},
                }
            )

        yield from responses

    def send_delta_message(
        self, msg_id: str, content: str, channel_uuid: str, contact_urn: str, **kwargs
    ) -> Dict[str, Any]:
        """Mock delta message send."""
        self.calls.append(
            {
                "method": "send_delta_message",
                "msg_id": msg_id,
                "content": content,
            }
        )

        return {
            "status": "success",
            "msg_id": msg_id,
            "message": f"Mock delta acknowledged: {content[:30]}",
            "sequence": len(self.calls),
            "is_final": False,
            "data": {},
        }

    def send_completed_message(
        self, msg_id: str, content: str, channel_uuid: str, contact_urn: str, **kwargs
    ) -> Dict[str, Any]:
        """Mock completed message send."""
        self.calls.append(
            {
                "method": "send_completed_message",
                "msg_id": msg_id,
                "content": content,
            }
        )

        return {
            "status": "success",
            "msg_id": msg_id,
            "message": f"Mock completion: {content[:30]}",
            "sequence": len(self.calls),
            "is_final": True,
            "data": {},
        }

    def send_single_message(
        self, msg_id: str, channel_uuid: str, contact_urn: str, content: str, **kwargs
    ) -> Dict[str, Any]:
        """Mock single message send."""
        self.calls.append(
            {
                "method": "send_single_message",
                "msg_id": msg_id,
                "content": content,
            }
        )

        return {
            "status": "success",
            "msg_id": msg_id,
            "message": f"Mock response to: {content[:50]}",
            "sequence": 0,
            "is_final": True,
            "data": {},
        }

    def close(self):
        """Mock close - does nothing."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def create_mock_client_with_responses(responses: List[Dict[str, Any]]) -> MockMessageStreamingClient:
    """
    Create a mock client with custom responses.

    Args:
        responses: List of response dicts to yield

    Returns:
        MockMessageStreamingClient configured with custom responses

    Example:
        mock_client = create_mock_client_with_responses([
            {'status': 'success', 'message': 'Custom', 'is_final': True}
        ])
    """
    client = MockMessageStreamingClient()
    client.mock_responses = responses
    return client


def create_mock_error_client(error_message: str = "Mock error") -> MockMessageStreamingClient:
    """
    Create a mock client that returns errors.

    Example:
        mock_client = create_mock_error_client("Server unavailable")
    """
    client = MockMessageStreamingClient()
    client.connected = False
    client.mock_responses = [
        {
            "status": "error",
            "msg_id": "mock",
            "message": error_message,
            "sequence": 0,
            "is_final": True,
            "error_code": "UNAVAILABLE",
            "error_message": error_message,
            "data": {},
        }
    ]
    return client
