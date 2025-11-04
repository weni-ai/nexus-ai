import json

from calling.events.listener import EventListener
from calling.sessions import Session, SessionManager
from calling.sessions.session import Session


class SendWelcomeListener(EventListener):
    welcome_message = {
        "type": "response.create",
        "response": {
            "instructions": "Apresente-se, diga seu nome e como pode ajudar o contato. seja breve",
        },
    }

    async def perform(self, _: str, session: Session, **kwargs):
        datachannel = session.openai_datachannel

        if datachannel is None:
            SessionManager.close_session(session.call_id)
            return

        datachannel.send(json.dumps(self.welcome_message))