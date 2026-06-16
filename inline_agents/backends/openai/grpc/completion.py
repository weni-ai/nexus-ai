"""Final-message delivery for persistent WWC gRPC streams."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from inline_agents.backends.openai.grpc.streaming_client import MessageStreamingClient, StreamingSession

logger = logging.getLogger(__name__)

_MAX_RESPONSE_SUMMARY = 8


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
        logger.warning(
            "[OpenAIBackend] gRPC delivery skipped project_uuid=%s has_text=%s has_contact_urn=%s has_msg_id=%s",
            project_uuid,
            bool((text or "").strip()),
            bool(contact_urn),
            bool(grpc_msg_id),
        )
        return False

    session_active = bool(grpc_session and grpc_session.is_active)
    session_deltas = grpc_session.delta_count if grpc_session else 0
    logger.info(
        "[OpenAIBackend] gRPC delivery start project_uuid=%s msg_id=%s chars=%s " "session_active=%s session_deltas=%s",
        target.project_uuid,
        target.msg_id,
        len(target.text),
        session_active,
        session_deltas,
    )

    if session_active and _deliver_via_session(grpc_session, target):
        logger.info(
            "[OpenAIBackend] gRPC delivery outcome path=session project_uuid=%s msg_id=%s",
            target.project_uuid,
            target.msg_id,
        )
        return True

    logger.info(
        "[OpenAIBackend] gRPC delivery falling back to unary project_uuid=%s msg_id=%s " "session_was_active=%s",
        target.project_uuid,
        target.msg_id,
        session_active,
    )
    if _deliver_via_unary(grpc_client, target):
        logger.info(
            "[OpenAIBackend] gRPC delivery outcome path=unary project_uuid=%s msg_id=%s",
            target.project_uuid,
            target.msg_id,
        )
        return True

    logger.warning(
        "[OpenAIBackend] gRPC delivery outcome path=none project_uuid=%s msg_id=%s",
        target.project_uuid,
        target.msg_id,
    )
    return False


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
        return list(session._responses)


def _summarize_responses(responses: list[dict[str, Any]]) -> str:
    if not responses:
        return "(empty)"
    tail = responses[-_MAX_RESPONSE_SUMMARY:]
    offset = len(responses) - len(tail)
    parts: list[str] = []
    for index, resp in enumerate(tail):
        data = resp.get("data") or {}
        parts.append(
            f"#{offset + index} status={resp.get('status')!r} is_final={resp.get('is_final')} "
            f"received_type={data.get('received_type')!r} seq={resp.get('sequence')}"
        )
    prefix = f"{len(responses)} total, showing last {len(tail)}: "
    return prefix + "; ".join(parts)


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
                "[OpenAIBackend] gRPC send_completed rejected project_uuid=%s msg_id=%s "
                "session_deltas=%s stream_active=%s completed_sent=%s",
                target.project_uuid,
                target.msg_id,
                session.delta_count,
                session.is_active,
                session._completed_sent,
            )
            return False

        responses = _read_session_responses(session)
        if not _session_ack_success(responses):
            logger.warning(
                "[OpenAIBackend] gRPC send_completed missing success ack project_uuid=%s msg_id=%s " "responses=%s",
                target.project_uuid,
                target.msg_id,
                _summarize_responses(responses),
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
        responses = _read_session_responses(session)
        logger.error(
            "gRPC session completion failed project_uuid=%s msg_id=%s exc=%s responses=%s",
            target.project_uuid,
            target.msg_id,
            exc,
            _summarize_responses(responses),
            exc_info=True,
        )
        return False


def _deliver_via_unary(client: MessageStreamingClient | None, target: GrpcDeliveryTarget) -> bool:
    if client is None:
        logger.warning(
            "[OpenAIBackend] gRPC unary skipped (no client) project_uuid=%s msg_id=%s",
            target.project_uuid,
            target.msg_id,
        )
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
            "[OpenAIBackend] gRPC unary completed project_uuid=%s msg_id=%s chars=%s result=%s",
            target.project_uuid,
            target.msg_id,
            len(target.text),
            _summarize_unary_result(result),
        )
        return True

    logger.warning(
        "[OpenAIBackend] gRPC unary completion failed project_uuid=%s msg_id=%s result=%s",
        target.project_uuid,
        target.msg_id,
        _summarize_unary_result(result),
    )
    return False


def _summarize_unary_result(result: dict[str, Any] | None) -> str:
    if not result:
        return "(empty)"
    data = result.get("data") or {}
    return (
        f"status={result.get('status')!r} is_final={result.get('is_final')} "
        f"received_type={data.get('received_type')!r} seq={result.get('sequence')}"
    )
