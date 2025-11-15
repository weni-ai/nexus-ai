from django.conf import settings

from calling.clients.meta import accept_call
from calling.events.listener import EventListener
from calling.sessions import Session, SessionManager
from calling.sessions.session import Session


class AcceptCallListener(EventListener):
    async def perform(self, _: str, session: Session, **kwargs):
        if not session.answer_sdp:
            SessionManager.close_session(session.call_id)
            return

        await accept_call(
            session.answer_sdp,
            session.call_id,
            session.wa_phone_number_id,
            settings.WA_ACCESS_TOKEN
        )
