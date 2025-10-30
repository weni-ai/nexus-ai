import logging

from aiortc.contrib.media import MediaRelay
from aiortc.rtcdtlstransport import (
    RTCCertificate,
    RTCDtlsFingerprint,
    certificate_digest,
)

from calling.bridge import RTCBridge
from calling.clients.nexus import get_manager
from calling.events import EventRegistry
from calling.events.listeners.play_audio import PlayAudioListener
from calling.events.listeners.stop_audio import StopAudioListener
from calling.sessions import SessionManager

EventRegistry.subscribe("agent.run.started", PlayAudioListener())
EventRegistry.subscribe("agent.run.completed", StopAudioListener())

logger = logging.getLogger(__name__)


def getFingerprints_sha256(self):
    return [RTCDtlsFingerprint("sha-256", certificate_digest(self._cert, "sha-256"))]


RTCCertificate.getFingerprints = getFingerprints_sha256


relay = MediaRelay()


async def get_answer(sdp: str, call_id: str):
    message_dict = {
        "project_uuid": "aca2822c-06bd-4066-8ee9-c38c7e68839a",
        "text": "Sample",
        "contact_urn": "ext:260257732924@",
        "channel_uuid": "1029bbb8-2298-489c-ace7-09755a65f8df",
        "contact_name": "Sample Name",
    }

    agents = await get_manager(message_dict)


    session = SessionManager.setup_session(call_id, sdp)
    session.set_agents(agents)

    answer_sdp = await RTCBridge.handle_offer(session)

    return answer_sdp
