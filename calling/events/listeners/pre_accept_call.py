from django.conf import settings

from calling.clients.meta import pre_accept_call
from calling.events.listener import EventListener
from calling.sessions.session import Session


class PreAcceptCallListener(EventListener):
    async def perform(self, _: str, session: Session, **kwargs):
        await pre_accept_call(
            session.answer_sdp,
            session.call_id,
            settings.WA_PHONE_NUMBER,
            settings.WA_ACCESS_TOKEN
        )

