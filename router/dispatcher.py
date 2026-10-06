from typing import Dict, List

from router.direct_message import DirectMessage
from router.entities import (
    FlowDTO,
    Message,
)
from router.entities.mailroom import extract_ig_comment_broadcast_fields
from router.flow_start import FlowStart


def dispatch(
    message: Message,
    user_email: str,
    flow: FlowDTO = None,
    llm_response: str = None,
    direct_message: DirectMessage = None,
    flow_start: FlowStart = None,
    full_chunks: List[Dict] = None,
    backend: str = "BedrockBackend",
):
    urns = [message.contact_urn]

    if direct_message:
        ig_comment_fields = extract_ig_comment_broadcast_fields(getattr(message, "metadata", None))
        return direct_message.send_direct_message(
            llm_response,
            urns,
            message.project_uuid,
            user_email,
            full_chunks=full_chunks,
            backend=backend,
            channel_uuid=getattr(message, "channel_uuid", ""),
            **ig_comment_fields,
        )

    return flow_start.start_flow(
        flow=flow,
        user=user_email,
        urns=urns,
        user_message=message.text,
        llm_response=llm_response,
    )
