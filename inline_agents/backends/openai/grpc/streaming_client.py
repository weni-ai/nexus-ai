"""
gRPC client for streaming messages to external services.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

import grpc
from django.conf import settings

from inline_agents.backends.openai.grpc.generated import (
    message_stream_service_pb2,
    message_stream_service_pb2_grpc,
)

logger = logging.getLogger(__name__)

# ANSI color codes for gRPC logs - makes them easy to spot in terminal
CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Colored prefixes for easy identification
GRPC_PREFIX = f"{BOLD}{CYAN}[gRPC]{RESET}"
GRPC_OK = f"{GREEN}✓{RESET}"
GRPC_FAIL = f"{RED}✗{RESET}"
GRPC_HINT = f"{YELLOW}💡{RESET}"


def is_grpc_enabled() -> bool:
    return bool(settings.GRPC_ENABLED)


class MessageStreamingClient:
    """
    gRPC client for bidirectional message streaming.

    Usage:
        with MessageStreamingClient(host='service.com', port=50051) as client:
            for response in client.stream_messages_with_setup(...):
                logger.debug("Setup response", extra={"success": response.success, "message": response.message})
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 50051,
        use_secure_channel: bool = False,
        credentials: Optional[grpc.ChannelCredentials] = None,
        max_message_length: int = 100 * 1024 * 1024,
    ):
        """
        Initialize the streaming client.

        Args:
            host: Server hostname or IP
            port: Server port
            use_secure_channel: Use TLS/SSL (recommended for production)
            credentials: TLS credentials if use_secure_channel=True
            max_message_length: Max message size in bytes (default 100MB)
        """
        self.host = host
        self.port = port
        self.target = f"{host}:{port}"
        self.use_secure_channel = use_secure_channel

        options = [
            ("grpc.max_send_message_length", max_message_length),
            ("grpc.max_receive_message_length", max_message_length),
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.keepalive_permit_without_calls", True),
        ]

        if use_secure_channel:
            if credentials is None:
                credentials = grpc.ssl_channel_credentials()
            self.channel = grpc.secure_channel(self.target, credentials, options=options)
        else:
            self.channel = grpc.insecure_channel(self.target, options=options)

        self.stub = message_stream_service_pb2_grpc.MessageStreamServiceStub(self.channel)
        logger.info(
            f"{GRPC_PREFIX} {GRPC_OK} Client initialized | {CYAN}target={self.target}{RESET} | "
            f"secure={use_secure_channel} | max_msg_size={max_message_length}"
        )

    def check_connection(self, timeout: int = 5) -> bool:
        """Test if server is reachable."""
        try:
            grpc.channel_ready_future(self.channel).result(timeout=timeout)
            logger.info(f"{GRPC_PREFIX} {GRPC_OK} Connection OK | {CYAN}target={self.target}{RESET}")
            return True
        except grpc.FutureTimeoutError:
            logger.error(
                f"{GRPC_PREFIX} {GRPC_FAIL} {RED}Connection timeout{RESET} | "
                f"{CYAN}target={self.target}{RESET} | timeout={timeout}s | secure={self.use_secure_channel}"
            )
            return False
        except Exception as e:
            logger.error(
                f"{GRPC_PREFIX} {GRPC_FAIL} {RED}Connection failed{RESET} | "
                f"{CYAN}target={self.target}{RESET} | secure={self.use_secure_channel} | "
                f"error={type(e).__name__}: {e}"
            )
            return False

    def _log_grpc_error(self, operation: str, e: grpc.RpcError) -> None:
        """Log detailed gRPC error information for debugging."""
        error_code = e.code()
        error_details = e.details() or "No details"

        # Extract additional debug info if available
        debug_info = ""
        try:
            trailing_metadata = e.trailing_metadata()
            if trailing_metadata:
                debug_info = f" | trailing_metadata={dict(trailing_metadata)}"
        except Exception:
            pass

        # Common error explanations to help server owners debug
        error_hints = {
            grpc.StatusCode.UNAVAILABLE: (
                "Server unreachable. Check: 1) Server is running, 2) Host/port correct, "
                "3) Firewall/network allows connection, 4) TLS settings match"
            ),
            grpc.StatusCode.DEADLINE_EXCEEDED: "Request timed out. Server may be overloaded or slow.",
            grpc.StatusCode.UNAUTHENTICATED: "Authentication failed. Check credentials/tokens.",
            grpc.StatusCode.PERMISSION_DENIED: "Not authorized. Check permissions on server.",
            grpc.StatusCode.UNIMPLEMENTED: "Method not implemented on server. Check proto compatibility.",
            grpc.StatusCode.INTERNAL: "Server internal error. Check server logs.",
            grpc.StatusCode.RESOURCE_EXHAUSTED: "Server resources exhausted (rate limit, memory, etc).",
        }
        hint = error_hints.get(error_code, "")

        logger.error(
            f"{GRPC_PREFIX} {GRPC_FAIL} {RED}{operation} FAILED{RESET} | "
            f"{CYAN}target={self.target}{RESET} | secure={self.use_secure_channel} | "
            f"code={RED}{error_code.name}{RESET} ({error_code.value[0]}) | details={error_details}{debug_info}"
        )
        if hint:
            logger.error(f"{GRPC_PREFIX} {GRPC_HINT} {YELLOW}{hint}{RESET}")

    def send_setup_message(
        self,
        msg_id: str,
        channel_uuid: str,
        contact_urn: str,
        project_uuid: Optional[str] = None,
        config: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Send initial setup message (unary RPC).

        Returns dict with: success, session_id, message, error_message
        """
        logger.info(f"{GRPC_PREFIX} Sending setup | {CYAN}target={self.target}{RESET} | contact_urn={contact_urn}")

        request = message_stream_service_pb2.SetupRequest(
            msg_id=msg_id,
            channel_uuid=channel_uuid,
            contact_urn=contact_urn,
            project_uuid=project_uuid or "",
            config=config or {},
        )

        try:
            response = self.stub.Setup(request, timeout=30)
            logger.info(
                f"{GRPC_PREFIX} {GRPC_OK} Setup response | {GREEN}success={response.success}{RESET} | "
                f"session_id={response.session_id}"
            )
            return {
                "success": response.success,
                "session_id": response.session_id,
                "message": response.message,
                "error_message": response.error_message if not response.success else None,
            }
        except grpc.RpcError as e:
            self._log_grpc_error("Setup", e)
            return {
                "success": False,
                "session_id": None,
                "message": f"gRPC error: {e.code().name}",
                "error_message": e.details(),
            }

    def send_delta_message(
        self,
        msg_id: str,
        content: str,
        channel_uuid: str,
        contact_urn: str,
        project_uuid: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        Send a single delta message (unary RPC).

        Use this to send incremental updates after setup.
        Call this multiple times to send a stream of delta messages.

        Args:
            msg_id: Unique message ID for this delta
            content: The delta content to send
            channel_uuid: Channel UUID
            contact_urn: Contact URN
            project_uuid: Optional project UUID
            metadata: Optional metadata
            timeout: Request timeout in seconds

        Returns:
            Dict with: status, msg_id, message, sequence, is_final, data

        Example:
            # After setup, send multiple deltas
            for i, chunk in enumerate(content_chunks):
                response = client.send_delta_message(
                    msg_id=f"delta-{i}",
                    content=chunk,
                    channel_uuid="uuid",
                    contact_urn="whatsapp:+5511999999999"
                )
                logger.debug("Delta status", extra={"index": i, "status": response["status"]})
        """
        content_len = len(content) if content else 0
        logger.info(
            f"{GRPC_PREFIX} Sending delta | {CYAN}target={self.target}{RESET} | "
            f"msg_id={msg_id} | content_len={content_len}"
        )

        message = message_stream_service_pb2.StreamMessage(
            type="delta",
            msg_id=msg_id,
            content=content,
            channel_uuid=channel_uuid,
            contact_urn=contact_urn,
            project_uuid=project_uuid or "",
            metadata=metadata or {},
            timestamp=datetime.now().isoformat(),
        )

        try:
            response = self.stub.SendMessage(message, timeout=timeout)
            logger.info(
                f"{GRPC_PREFIX} {GRPC_OK} Delta sent | msg_id={msg_id} | {GREEN}status={response.status}{RESET}"
            )
            return {
                "status": response.status,
                "msg_id": response.msg_id,
                "message": response.message,
                "sequence": response.sequence,
                "is_final": response.is_final,
                "data": dict(response.data) if response.data else {},
            }
        except grpc.RpcError as e:
            self._log_grpc_error("Delta message", e)
            return {
                "status": "error",
                "msg_id": msg_id,
                "message": f"gRPC error: {e.code().name}",
                "error_code": e.code().name,
                "error_message": e.details(),
            }

    def send_completed_message(
        self,
        msg_id: str,
        content: str,
        channel_uuid: str,
        contact_urn: str,
        project_uuid: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        Send a completed message (unary RPC).

        Call this after all delta messages to signal completion.

        Args:
            msg_id: Unique message ID for completion
            content: Final content or summary
            channel_uuid: Channel UUID
            contact_urn: Contact URN
            project_uuid: Optional project UUID
            metadata: Optional metadata
            timeout: Request timeout in seconds

        Returns:
            Dict with: status, msg_id, message, sequence, is_final, data

        Example:
            # Send setup
            for _ in client.stream_messages_with_setup(...):
                pass

            # Send deltas
            for chunk in chunks:
                client.send_delta_message(...)

            # Send completion
            response = client.send_completed_message(
                msg_id="session-123",
                content="Streaming complete",
                channel_uuid="uuid",
                contact_urn="whatsapp:+5511999999999"
            )
            logger.debug("Completed status", extra={"status": response["status"]})
        """
        content_len = len(content) if content else 0
        logger.info(
            f"{GRPC_PREFIX} Sending completed | {CYAN}target={self.target}{RESET} | "
            f"msg_id={msg_id} | content_len={content_len}"
        )

        message = message_stream_service_pb2.StreamMessage(
            type="completed",
            msg_id=msg_id,
            content=content,
            channel_uuid=channel_uuid,
            contact_urn=contact_urn,
            project_uuid=project_uuid or "",
            metadata=metadata or {},
            timestamp=datetime.now().isoformat(),
        )

        try:
            response = self.stub.SendMessage(message, timeout=timeout)
            logger.info(
                f"{GRPC_PREFIX} {GRPC_OK} Completed sent | msg_id={msg_id} | {GREEN}status={response.status}{RESET}"
            )
            return {
                "status": response.status,
                "msg_id": response.msg_id,
                "message": response.message,
                "sequence": response.sequence,
                "is_final": response.is_final,
                "data": dict(response.data) if response.data else {},
            }
        except grpc.RpcError as e:
            self._log_grpc_error("Completed message", e)
            return {
                "status": "error",
                "msg_id": msg_id,
                "message": f"gRPC error: {e.code().name}",
                "error_code": e.code().name,
                "error_message": e.details(),
            }

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
        Stream messages with automatic setup (bidirectional streaming).

        Automatically sends setup message first, then optional content messages.

        Args:
            msg_id: Unique message ID
            channel_uuid: Channel UUID
            contact_urn: Contact URN (e.g. "whatsapp:+5511999999999")
            messages: Optional list of messages to send after setup
            project_uuid: Optional project UUID
            metadata: Optional additional metadata

        Yields:
            Dict with: status, msg_id, message, sequence, is_final, error_code, error_message, data

        Example:
            for response in client.stream_messages_with_setup(
                msg_id="abc123",
                channel_uuid="uuid-456",
                contact_urn="whatsapp:+5511999999999",
                messages=["Hello!"]
            ):
                print(response['message'])
                if response['is_final']:
                    break
        """
        logger.info(
            f"{GRPC_PREFIX} Starting stream | {CYAN}target={self.target}{RESET} | "
            f"contact_urn={contact_urn} | msg_id={msg_id}"
        )

        def message_generator():
            """Generate messages to stream."""
            # Setup message (always first)
            setup_msg = message_stream_service_pb2.StreamMessage(
                type="setup",
                msg_id=msg_id,
                content="",
                channel_uuid=channel_uuid,
                contact_urn=contact_urn,
                project_uuid=project_uuid or "",
                metadata=metadata or {},
                timestamp=datetime.now().isoformat(),
            )
            yield setup_msg

            # Content messages (if any)
            if messages:
                for idx, content in enumerate(messages):
                    content_msg = message_stream_service_pb2.StreamMessage(
                        type="content",
                        msg_id=f"{msg_id}-content-{idx+1}",
                        content=content,
                        channel_uuid=channel_uuid,
                        contact_urn=contact_urn,
                        project_uuid=project_uuid or "",
                        metadata=metadata or {},
                        timestamp=datetime.now().isoformat(),
                    )
                    yield content_msg

        try:
            response_iterator = self.stub.StreamMessages(message_generator())

            for response in response_iterator:
                result = {
                    "status": response.status,
                    "msg_id": response.msg_id,
                    "message": response.message,
                    "sequence": response.sequence,
                    "is_final": response.is_final,
                    "error_code": response.error_code if response.error_code else None,
                    "error_message": response.error_message if response.error_message else None,
                    "data": dict(response.data) if response.data else {},
                }
                logger.debug("Stream response", extra={"sequence": result["sequence"], "status": result["status"]})
                yield result

                if response.is_final:
                    break

        except grpc.RpcError as e:
            self._log_grpc_error("Streaming", e)
            yield {
                "status": "error",
                "msg_id": msg_id,
                "message": f"gRPC error: {e.code().name}",
                "sequence": -1,
                "is_final": True,
                "error_code": e.code().name,
                "error_message": e.details(),
                "data": {},
            }

    def send_single_message(
        self,
        msg_id: str,
        channel_uuid: str,
        contact_urn: str,
        content: str,
        message_type: str = "content",
        project_uuid: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Send a single message (unary RPC)."""
        logger.info(f"{GRPC_PREFIX} Sending single message | {CYAN}target={self.target}{RESET} | msg_id={msg_id}")

        message = message_stream_service_pb2.StreamMessage(
            type=message_type,
            msg_id=msg_id,
            content=content,
            channel_uuid=channel_uuid,
            contact_urn=contact_urn,
            project_uuid=project_uuid or "",
            metadata=metadata or {},
            timestamp=datetime.now().isoformat(),
        )

        try:
            response = self.stub.SendMessage(message, timeout=30)
            logger.info(
                f"{GRPC_PREFIX} {GRPC_OK} Single message sent | msg_id={msg_id} | {GREEN}status={response.status}{RESET}"
            )
            return {
                "status": response.status,
                "msg_id": response.msg_id,
                "message": response.message,
                "sequence": response.sequence,
                "is_final": response.is_final,
                "data": dict(response.data) if response.data else {},
            }
        except grpc.RpcError as e:
            self._log_grpc_error("Single message", e)
            return {
                "status": "error",
                "msg_id": msg_id,
                "message": f"gRPC error: {e.code().name}",
                "error_code": e.code().name,
                "error_message": e.details(),
            }

    def close(self):
        """Close the gRPC channel."""
        if self.channel:
            logger.info(f"{GRPC_PREFIX} Closing channel | {CYAN}target={self.target}{RESET}")
            self.channel.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        self.close()
