import asyncio

from calling.events.listener import EventListener
from calling.sessions.session import Session


class StopAudioListener(EventListener):
    async def perform(self, _, session: Session, **kwargs):
        await asyncio.sleep(0.1)

        audio_player = getattr(session, "audio_player", None)
        if audio_player is not None:
            try:
                print("Parando MediaPlayer")
                if hasattr(audio_player, '_stop'):
                    audio_player._stop()
                # Limpar referência
                session.audio_player = None
            except Exception as e:
                print(f"Error stopping MediaPlayer:: {e}")

        wpp_audio_track = getattr(session, "wpp_audio_track", None)

        if wpp_audio_track is not None and session.wpp_audio_sender != session.wpp_audio_track:
            session.wpp_audio_sender.replaceTrack(session.wpp_audio_track)