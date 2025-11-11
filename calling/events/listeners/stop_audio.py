import asyncio

from calling.events.listener import EventListener
from calling.sessions.session import Session


class StopAudioListener(EventListener):
    async def perform(self, _, session: Session, **kwargs):
        await asyncio.sleep(0.1)

        wpp_audio_track = getattr(session, "wpp_audio_track", None)

        if wpp_audio_track is not None and session.wpp_audio_sender != session.wpp_audio_track:
            session.wpp_audio_sender.replaceTrack(session.wpp_audio_track)