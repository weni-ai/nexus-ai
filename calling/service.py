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
from calling.events import EventRegistry
from calling.events.listeners import (
    AcceptCallListener,
    PlayAudioListener,
    PreAcceptCallListener,
    SendWelcomeListener,
    StopAudioListener,
)
from calling.sessions import SessionManager, Session
from calling.api_models import CallsModel, BusinessInitiatedCallsModel
from calling.clients.meta import start_business_initiated_call

from django.conf import settings


EventRegistry.subscribe("agent.run.started", PlayAudioListener())
EventRegistry.subscribe("agent.run.completed", StopAudioListener())
EventRegistry.subscribe("contact.speech.started", StopAudioListener())
EventRegistry.subscribe("whatspp.answer.created", PreAcceptCallListener())

EventRegistry.subscribe("openai.session.updated", SendWelcomeListener())



def getFingerprints_sha256(self):
    return [RTCDtlsFingerprint("sha-256", certificate_digest(self._cert, "sha-256"))]


RTCCertificate.getFingerprints = getFingerprints_sha256


relay = MediaRelay()

def temp_decode_agents(team: str) -> dict:
    decoded = base64.b64decode(team)
    return pickle.loads(decoded)


class CallingService:

    @staticmethod
    async def dispatch_business_initiated(session: Session, body: CallsModel):
        session.set_answer_sdp(body.call.session.sdp)

        await RTCBridge.handle_business_initiated(session)

    @staticmethod
    async def start_business_initiated(body: BusinessInitiatedCallsModel):
        phone_number_id = phone_number_mapping.get(body.project_uuid)
        
        contact_urn = body.contact_urn
        project_uuid = body.project_uuid

        message_dict = {
            "project_uuid": project_uuid,
            "contact_urn": contact_urn,
            "channel_uuid": "", # TODO: Receber o uuid do canal
            "contact_fields": {},  # TODO: enviar
            "contact_name": "",
            "text": ""
        }

        session = SessionManager.setup_business_initiated_session(phone_number_id, project_uuid, contact_urn)
        start_calling(session, message_dict)

        phone_number = session.contact_urn.replace("whatsapp:", "")

        wpp_connection = session.wpp_connection

        wpp_connection.addTransceiver("audio", direction="sendrecv")

        offer = await wpp_connection.createOffer()
        await wpp_connection.setLocalDescription(offer)

        sdp_offer = wpp_connection.localDescription.sdp

        response = await start_business_initiated_call(phone_number, sdp_offer, session.wa_phone_number_id, settings.WA_ACCESS_TOKEN)

        if not response:
            print("Not RESPONSE", response)
            # TODO
            return

        calls = response.get("calls")

        if calls is None:
            print("Not call_id", response)
            return

        session.call_id = calls[0].get("id")
        SessionManager._add_active_session(session)

        print("Call id sette", session.call_id)

        # await RTCBridge.handle_business_initiated(session)

    @staticmethod
    async def dispatch(body: CallsModel) -> None:
        call = body.call
        call_id = call.call_id

        contact_urn = f"whatsapp:{call.from_number}"

        message_dict = {
            "project_uuid": body.project_uuid,
            "contact_urn": contact_urn,
            "channel_uuid": body.channel_uuid,
            "contact_fields": {},  # TODO: enviar
            "contact_name": body.name,
            "text": ""
        }

        session = SessionManager.setup_session(call_id, body.phone_number_id, body.project_uuid, contact_urn,offer_sdp=call.session.sdp)
        start_calling(session, message_dict)

        await RTCBridge.handle_offer(session)
