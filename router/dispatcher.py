from typing import List, Dict

from router.entities import (
    Message,
    FlowDTO,
)
from router.direct_message import DirectMessage
from router.flow_start import FlowStart


def dispatch(
        message: Message,
        user_email: str,
        flow: FlowDTO = None,
        llm_response: str = None,
        direct_message: DirectMessage = None,
        flow_start: FlowStart = None,
        full_chunks: List[Dict] = None,
        backend: str = "BedrockBackend"
):
    urns = [message.contact_urn]

    if direct_message:
        return direct_message.send_direct_message(
            llm_response,
            urns,
            message.project_uuid,
            user_email,
            full_chunks=full_chunks,
            backend=backend
        )

    return flow_start.start_flow(
        flow=flow,
        user=user_email,
        urns=urns,
        user_message=message.text,
        llm_response=llm_response,
    )
