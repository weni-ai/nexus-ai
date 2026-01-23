"""
gRPC client for streaming messages to external services.

This module provides a persistent bidirectional streaming client that maintains
a single connection for setup, deltas, and completed messages.
"""

import logging
import queue
import threading
from datetime import datetime
from typing import Any, Callable, Dict, Iterator, List, Optional

import grpc
from django.conf import settings

from inline_agents.backends.openai.grpc.generated import (
    message_stream_service_pb2,
    message_stream_service_pb2_grpc,
)

logger = logging.getLogger(__name__)


def is_grpc_enabled(project_uuid: str, use_components: bool, stream_support: bool) -> bool:
    """
    Check if GRPC is enabled for a project.

    Set GRPC_ENABLED_PROJECTS=["uuid1", "uuid2"] or ["*"] for all projects.
    """
    if use_components or not stream_support:
        return False
    enabled_projects = getattr(settings, "GRPC_ENABLED_PROJECTS", [])
    return str(project_uuid) in enabled_projects or "*" in enabled_projects


class StreamingSession:
    """
    A persistent bidirectional streaming session.

    Keeps a single gRPC stream open for the entire agent invocation,
    allowing setup, deltas, and completed messages to flow through
    the same connection with minimal latency.

    Usage:
        session = client.create_streaming_session(
            msg_id="abc123",
            channel_uuid="uuid",
            contact_urn="whatsapp:+55...",
            project_uuid="proj-uuid"
        )

        # Setup is sent automatically when starting
        session.start()

        # Send deltas through the same connection
        session.send_delta("Hello ")
        session.send_delta("world!")

        # Send completed and close
        session.send_completed("Hello world!")
    """

    def __init__(
        self,
        stub: message_stream_service_pb2_grpc.MessageStreamServiceStub,
        msg_id: str,
        channel_uuid: str,
        contact_urn: str,
        project_uuid: str = "",
        metadata: Optional[Dict[str, str]] = None,
        on_response: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.stub = stub
        self.msg_id = msg_id
        self.channel_uuid = channel_uuid
        self.contact_urn = contact_urn
        self.project_uuid = project_uuid
        self.metadata = metadata or {}
        self.on_response = on_response

        self._message_queue: queue.Queue = queue.Queue()
        self._response_thread: Optional[threading.Thread] = None
        self._stream_active = False
        self._setup_complete = False
        self._delta_counter = 0
        self._lock = threading.Lock()
        self._responses: List[Dict[str, Any]] = []
        self._error: Optional[Exception] = None

    def _create_message(self, msg_type: str, content: str = "") -> message_stream_service_pb2.StreamMessage:
        """Create a StreamMessage with the given type and content."""
        return message_stream_service_pb2.StreamMessage(
            type=msg_type,
            msg_id=self.msg_id,
            content=content,
            channel_uuid=self.channel_uuid,
            contact_urn=self.contact_urn,
            project_uuid=self.project_uuid,
            metadata=self.metadata,
            timestamp=datetime.now().isoformat(),
        )

    def _message_generator(self) -> Iterator[message_stream_service_pb2.StreamMessage]:
        """Generator that yields messages from the queue."""
        # First, send the setup message
        setup_msg = self._create_message("setup", "")
        logger.info(f"[gRPC Session] Sending setup for {self.contact_urn}")
        yield setup_msg

        # Then yield messages from the queue until we get a stop signal
        while True:
            try:
                msg = self._message_queue.get(timeout=60)
                if msg is None:
                    # Stop signal received
                    logger.debug("[gRPC Session] Generator stopping - received stop signal")
                    break
                yield msg
            except queue.Empty:
                # Timeout - check if stream is still active
                if not self._stream_active:
                    break
                continue

    def _process_responses(self, response_iterator):
        """Process responses from the server in a background thread."""
        try:
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

                with self._lock:
                    self._responses.append(result)

                    # Mark setup as complete after first response
                    if not self._setup_complete:
                        self._setup_complete = True
                        logger.info(f"[gRPC Session] Setup complete: {result['status']}")

                # Call response callback if provided
                if self.on_response:
                    try:
                        self.on_response(result)
                    except Exception as e:
                        logger.error(f"[gRPC Session] Response callback error: {e}")

                if response.is_final:
                    break

        except grpc.RpcError as e:
            logger.error(f"[gRPC Session] Stream error: {e.code()} - {e.details()}")
            self._error = e
        except Exception as e:
            logger.error(f"[gRPC Session] Unexpected error: {e}")
            self._error = e
        finally:
            self._stream_active = False

    def start(self) -> bool:
        """
        Start the streaming session.

        Opens the bidirectional stream and sends the setup message.
        Returns True if setup was successful, False otherwise.
        """
        if self._stream_active:
            logger.warning("[gRPC Session] Session already active")
            return True

        try:
            self._stream_active = True
            self._setup_complete = False
            self._error = None
            self._responses = []

            # Start the bidirectional stream
            response_iterator = self.stub.StreamMessages(self._message_generator())

            # Process responses in a background thread
            self._response_thread = threading.Thread(
                target=self._process_responses,
                args=(response_iterator,),
                daemon=True,
            )
            self._response_thread.start()

            # Wait for setup to complete (with timeout)
            timeout = 10
            start_time = datetime.now()
            while not self._setup_complete and self._stream_active:
                if (datetime.now() - start_time).total_seconds() > timeout:
                    logger.error("[gRPC Session] Setup timeout")
                    self.close()
                    return False
                threading.Event().wait(0.01)

            if self._error:
                return False

            return self._setup_complete

        except grpc.RpcError as e:
            logger.error(f"[gRPC Session] Failed to start: {e.code()} - {e.details()}")
            self._stream_active = False
            self._error = e
            return False
        except Exception as e:
            logger.error(f"[gRPC Session] Failed to start: {e}")
            self._stream_active = False
            self._error = e
            return False

    def send_delta(self, content: str) -> bool:
        """
        Send a delta message through the persistent stream.

        Args:
            content: The delta content to send

        Returns:
            True if the message was queued successfully, False if the stream is not active
        """
        if not self._stream_active:
            logger.warning("[gRPC Session] Cannot send delta - stream not active")
            return False

        self._delta_counter += 1
        delta_msg = self._create_message("delta", content)
        self._message_queue.put(delta_msg)
        logger.debug(f"[gRPC Session] Queued delta #{self._delta_counter}")
        return True

    def send_completed(self, content: str) -> bool:
        """
        Send a completed message and close the stream.

        Args:
            content: The final completed content

        Returns:
            True if the message was sent successfully
        """
        if not self._stream_active:
            logger.warning("[gRPC Session] Cannot send completed - stream not active")
            return False

        logger.info(f"[gRPC Session] Sending completed message ({len(content)} chars)")
        completed_msg = self._create_message("completed", content)
        self._message_queue.put(completed_msg)

        # Signal the generator to stop
        self._message_queue.put(None)

        # Wait for response thread to finish
        if self._response_thread and self._response_thread.is_alive():
            self._response_thread.join(timeout=5)

        self._stream_active = False
        return True

    def close(self):
        """Close the streaming session."""
        if self._stream_active:
            logger.info("[gRPC Session] Closing session")
            self._stream_active = False
            self._message_queue.put(None)

            if self._response_thread and self._response_thread.is_alive():
                self._response_thread.join(timeout=2)

    @property
    def is_active(self) -> bool:
        """Check if the session is active."""
        return self._stream_active

    @property
    def delta_count(self) -> int:
        """Get the number of deltas sent."""
        return self._delta_counter

    @property
    def responses(self) -> List[Dict[str, Any]]:
        """Get all responses received."""
        with self._lock:
            return list(self._responses)

    @property
    def last_error(self) -> Optional[Exception]:
        """Get the last error, if any."""
        return self._error


class MessageStreamingClient:
    """
    gRPC client for bidirectional message streaming.

    Supports two modes:
    1. Persistent session (recommended): Create a StreamingSession for the entire
       agent invocation, sending setup, deltas, and completed through one connection.
    2. Legacy unary calls: Individual RPC calls for each message type.

    Usage (Persistent Session - Recommended):
        client = MessageStreamingClient(host='service.com', port=50051)
        session = client.create_streaming_session(
            msg_id="abc123",
            channel_uuid="uuid",
            contact_urn="whatsapp:+55...",
            project_uuid="proj-uuid"
        )
        session.start()
        session.send_delta("Hello ")
        session.send_delta("world!")
        session.send_completed("Hello world!")
        client.close()

    Usage (Legacy Unary):
        with MessageStreamingClient(host='service.com', port=50051) as client:
            client.send_setup_message(...)
            client.send_delta_message(...)
            client.send_completed_message(...)
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
        self._active_session: Optional[StreamingSession] = None
        logger.info(f"[gRPC Client] Initialized for {self.target}")

    def check_connection(self, timeout: int = 5) -> bool:
        """Test if server is reachable."""
        try:
            grpc.channel_ready_future(self.channel).result(timeout=timeout)
            return True
        except Exception as e:
            logger.error(f"[gRPC Client] Connection failed: {e}")
            return False

    def create_streaming_session(
        self,
        msg_id: str,
        channel_uuid: str,
        contact_urn: str,
        project_uuid: str = "",
        metadata: Optional[Dict[str, str]] = None,
        on_response: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> StreamingSession:
        """
        Create a new persistent streaming session.

        The session keeps a single bidirectional stream open for all messages,
        reducing latency significantly compared to unary calls.

        Args:
            msg_id: Unique message ID for this session
            channel_uuid: Channel UUID
            contact_urn: Contact URN (e.g. "whatsapp:+5511999999999")
            project_uuid: Optional project UUID
            metadata: Optional metadata to include with all messages
            on_response: Optional callback for each server response

        Returns:
            StreamingSession that can be used to send messages

        Example:
            session = client.create_streaming_session(
                msg_id="abc123",
                channel_uuid="uuid",
                contact_urn="whatsapp:+55...",
                project_uuid="proj-uuid"
            )
            if session.start():
                session.send_delta("Hello ")
                session.send_delta("world!")
                session.send_completed("Hello world!")
        """
        # Close any existing session
        if self._active_session and self._active_session.is_active:
            self._active_session.close()

        session = StreamingSession(
            stub=self.stub,
            msg_id=msg_id,
            channel_uuid=channel_uuid,
            contact_urn=contact_urn,
            project_uuid=project_uuid,
            metadata=metadata,
            on_response=on_response,
        )
        self._active_session = session
        return session

    # ============================================================
    # Legacy unary methods (kept for backwards compatibility)
    # ============================================================

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

        Note: Consider using create_streaming_session() for better performance.

        Returns dict with: success, session_id, message, error_message
        """
        logger.info(f"[gRPC Client] Sending setup for {contact_urn}")

        request = message_stream_service_pb2.SetupRequest(
            msg_id=msg_id,
            channel_uuid=channel_uuid,
            contact_urn=contact_urn,
            project_uuid=project_uuid or "",
            config=config or {},
        )

        try:
            response = self.stub.Setup(request, timeout=30)
            return {
                "success": response.success,
                "session_id": response.session_id,
                "message": response.message,
                "error_message": response.error_message if not response.success else None,
            }
        except grpc.RpcError as e:
            logger.error(f"[gRPC Client] Setup error: {e.code()} - {e.details()}")
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

        Note: Consider using create_streaming_session() for better performance
        when sending multiple deltas.
        """
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
            return {
                "status": response.status,
                "msg_id": response.msg_id,
                "message": response.message,
                "sequence": response.sequence,
                "is_final": response.is_final,
                "data": dict(response.data) if response.data else {},
            }
        except grpc.RpcError as e:
            logger.error(f"[gRPC Client] Delta error: {e.code()} - {e.details()}")
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

        Note: Consider using create_streaming_session() for better performance.
        """
        logger.info(f"[gRPC Client] Sending completed: {msg_id}")

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
            return {
                "status": response.status,
                "msg_id": response.msg_id,
                "message": response.message,
                "sequence": response.sequence,
                "is_final": response.is_final,
                "data": dict(response.data) if response.data else {},
            }
        except grpc.RpcError as e:
            logger.error(f"[gRPC Client] Completed error: {e.code()} - {e.details()}")
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

        DEPRECATED: Use create_streaming_session() instead for persistent streaming.

        This method opens and closes a stream for each call.
        For better performance with multiple deltas, use:

            session = client.create_streaming_session(...)
            session.start()
            session.send_delta(...)
            session.send_completed(...)
        """
        logger.info(f"[gRPC Client] Starting stream for {contact_urn}")

        def message_generator():
            """Generate messages to stream."""
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
                yield result

                if response.is_final:
                    break

        except grpc.RpcError as e:
            logger.error(f"[gRPC Client] Streaming error: {e.code()} - {e.details()}")
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

    def close(self):
        """Close the gRPC channel and any active session."""
        if self._active_session and self._active_session.is_active:
            self._active_session.close()
            self._active_session = None

        if self.channel:
            logger.info(f"[gRPC Client] Closing channel to {self.target}")
            self.channel.close()
            self.channel = None  # Prevent double-close logging from __del__

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        self.close()
