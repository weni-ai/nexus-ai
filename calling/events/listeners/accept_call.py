from calling.events.listener import EventListener
from calling.sessions.session import Session


class AcceptCallListener(EventListener):
    def perform(self, event_key: str, session: Session, **kwargs):
        pass
