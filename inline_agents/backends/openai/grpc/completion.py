"""Final-message delivery for persistent WWC gRPC streams."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from inline_agents.backends.openai.grpc.streaming_client import MessageStreamingClient, StreamingSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GrpcDeliveryTarget:
    project_uuid: str
    msg_id: str
    channel_uuid: str
    contact_urn: str
    text: str


def deliver_final_grpc_stream(
    text: str,
    *,
    grpc_client: MessageStreamingClient | None,
    grpc_session: StreamingSession | None,
    grpc_msg_id: str | None,
    channel_uuid: str,
    contact_urn: str,
    project_uuid: str,
) -> bool:
    """
    Send the final agent response on the WWC gRPC stream.

    Uses the persistent session when active; otherwise unary SendMessage.
    Returns False when delivery cannot be confirmed so HTTP dispatch can run.
    """
    target = _build_delivery_target(
        text=text,
        grpc_msg_id=grpc_msg_id,
        channel_uuid=channel_uuid,
        contact_urn=contact_urn,
        project_uuid=project_uuid,
    )
    if target is None:
        return False

    if grpc_session and grpc_session.is_active and _deliver_via_session(grpc_session, target):
        return True

    return _deliver_via_unary(grpc_client, target)


def _build_delivery_target(
    *,
    text: str,
    grpc_msg_id: str | None,
    channel_uuid: str,
    contact_urn: str,
    project_uuid: str,
) -> GrpcDeliveryTarget | None:
    if not (text or "").strip() or not contact_urn or not grpc_msg_id:
        return None
    return GrpcDeliveryTarget(
        project_uuid=str(project_uuid),
        msg_id=grpc_msg_id,
        channel_uuid=channel_uuid or "default-channel-uuid",
        contact_urn=contact_urn,
        text=text,
    )


def _read_session_responses(session: StreamingSession) -> list[dict[str, Any]]:
    with session._lock:
        return list(session.responses)


def _session_ack_success(responses: list[dict[str, Any]]) -> bool:
    if not responses:
        return False
    for resp in reversed(responses):
        received_type = (resp.get("data") or {}).get("received_type")
        if resp.get("is_final") or received_type == "completed":
            return resp.get("status") == "success"
    return responses[-1].get("status") == "success"


def _deliver_via_session(session: StreamingSession, target: GrpcDeliveryTarget) -> bool:
    try:
        if not session.send_completed(target.text):
            logger.warning(
                "[OpenAIBackend] gRPC send_completed rejected project_uuid=%s msg_id=%s",
                target.project_uuid,
                target.msg_id,
            )
            return False
        if not _session_ack_success(_read_session_responses(session)):
            logger.warning(
                "[OpenAIBackend] gRPC send_completed missing success ack project_uuid=%s msg_id=%s",
                target.project_uuid,
                target.msg_id,
            )
            return False
        logger.info(
            "[OpenAIBackend] gRPC stream completed project_uuid=%s msg_id=%s chars=%s",
            target.project_uuid,
            target.msg_id,
            len(target.text),
        )
        return True
    except Exception as exc:
        logger.error("gRPC session completion failed: %s", exc, exc_info=True)
        return False


def _deliver_via_unary(client: MessageStreamingClient | None, target: GrpcDeliveryTarget) -> bool:
    if client is None:
        return False
    try:
        result = client.send_completed_message(
            msg_id=target.msg_id,
            content=target.text,
            channel_uuid=target.channel_uuid,
            contact_urn=target.contact_urn,
            project_uuid=target.project_uuid,
        )
    except Exception as exc:
        logger.error("gRPC unary completion failed: %s", exc, exc_info=True)
        return False

    if (result or {}).get("status") == "success":
        logger.info(
            "[OpenAIBackend] gRPC unary completed project_uuid=%s msg_id=%s chars=%s",
            target.project_uuid,
            target.msg_id,
            len(target.text),
        )
        return True

    logger.warning(
        "[OpenAIBackend] gRPC unary completion failed project_uuid=%s msg_id=%s result=%s",
        target.project_uuid,
        target.msg_id,
        result,
    )
    return False
