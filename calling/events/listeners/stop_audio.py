import asyncio

from calling.events.listener import EventListener
from calling.sessions.session import Session


class StopAudioListener(EventListener):
    async def perform(self, _, session: Session, **kwargs):
        await asyncio.sleep(0.1)

        session.wpp_audio_sender.replaceTrack(session.wpp_audio_track)