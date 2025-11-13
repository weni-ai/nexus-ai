from django.conf import settings

from calling.clients.meta import pre_accept_call
from calling.events import EventRegistry
from calling.events.listener import EventListener
from calling.sessions import Session, SessionManager


class PreAcceptCallListener(EventListener):
    async def perform(self, _: str, session: Session, **kwargs):
        if not session.answer_sdp:
            SessionManager.close_session(session.call_id)
            return

        await pre_accept_call(
            session.answer_sdp,
            session.call_id,
            settings.WA_PHONE_NUMBER,
            settings.WA_ACCESS_TOKEN
        )

        await EventRegistry.notify("whatsapp.call.pre-accepted", session)


