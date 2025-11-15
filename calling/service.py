import base64
import pickle

from aiortc.contrib.media import MediaRelay
from aiortc.rtcdtlstransport import (
    RTCCertificate,
    RTCDtlsFingerprint,
    certificate_digest,
)

from router.tasks.invoke import start_calling

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
from calling.api_models import CallsModel


EventRegistry.subscribe("agent.run.started", PlayAudioListener())
EventRegistry.subscribe("agent.run.completed", StopAudioListener())
EventRegistry.subscribe("contact.speech.started", StopAudioListener())
EventRegistry.subscribe("whatspp.answer.created", PreAcceptCallListener())
# EventRegistry.subscribe("whatsapp.call.pre-accepted", AcceptCallListener())
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
    async def dispatch(body: CallsModel) -> None:
        call = body.call
        call_id = call.call_id


        contact_urn = f"whatsapp:{call.to}"

        message_dict = {
            "project_uuid": body.project_uuid,
            "contact_urn": contact_urn,
            "channel_uuid": body.channel_uuid,
            "contact_fields": {},  # TODO: enviar
            "contact_name": body.name,
            "text": ""
        }

        session = SessionManager.setup_session(call_id, call.session.sdp, body.phone_number_id)
        start_calling(session, message_dict)

        await RTCBridge.handle_offer(session)
