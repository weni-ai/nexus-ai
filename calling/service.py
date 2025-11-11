import base64
import pickle

from aiortc.contrib.media import MediaRelay
from aiortc.rtcdtlstransport import (
    RTCCertificate,
    RTCDtlsFingerprint,
    certificate_digest,
)

from calling.bridge import RTCBridge
from calling.clients.nexus import get_agents
from calling.events import EventRegistry
from calling.events.listeners import (
    AcceptCallListener,
    PlayAudioListener,
    PreAcceptCallListener,
    SendWelcomeListener,
    StopAudioListener,
)
from calling.sessions import SessionManager

EventRegistry.subscribe("agent.run.started", PlayAudioListener())
EventRegistry.subscribe("agent.run.completed", StopAudioListener())
EventRegistry.subscribe("contact.speech.started", StopAudioListener())
EventRegistry.subscribe("whatspp.answer.created", PreAcceptCallListener())
EventRegistry.subscribe("openai.channel.opened", AcceptCallListener())
EventRegistry.subscribe("whatsapp.remote.connected", SendWelcomeListener())



def getFingerprints_sha256(self):
    return [RTCDtlsFingerprint("sha-256", certificate_digest(self._cert, "sha-256"))]


RTCCertificate.getFingerprints = getFingerprints_sha256


relay = MediaRelay()

def temp_decode_agents(team: str) -> dict:
    decoded = base64.b64decode(team)
    return pickle.loads(decoded)


class CallingService:

    @staticmethod
    async def dispatch(sdp: str, call_id: str) -> None:
        message_dict = {
            "project_uuid": "b603aaf0-6e8b-4de7-8d96-8ee08c139780",
            "text": "Sample",
            "contact_urn": "ext:260257732924@",
            "channel_uuid": "1029bbb8-2298-489c-ace7-09755a65f8df",
            "contact_name": "Sample Name",
        }

        await get_agents(message_dict)

        session = SessionManager.setup_session(call_id, sdp)

        await RTCBridge.handle_offer(session)
