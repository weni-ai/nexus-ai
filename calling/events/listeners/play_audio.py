import asyncio
import time

from aiortc.contrib.media import MediaPlayer

from calling.events.listener import EventListener
from calling.sessions.session import Session

audio_file = "calling/sounds/waiting_sound.mp3"

class PlayAudioListener(EventListener):
    async def perform(self, _, session: Session, **kwargs):
        wpp_audio_sender = session.wpp_audio_sender

        if wpp_audio_sender is not None:
            old_player = getattr(session, "audio_player", None)

            if old_player is not None:
                try:
                    if hasattr(old_player, '_stop'):
                        old_player._stop()
                except Exception as e:
                    print(f"Error stopping previous player: {e}")

            player = MediaPlayer(audio_file, loop=True)
            outgoing_track = player.audio

            session.audio_player = player

            await asyncio.sleep(0.01)

            session.set_wpp_audio_track(wpp_audio_sender.track)

            print("Iniciando Musica")
            wpp_audio_sender.replaceTrack(outgoing_track)
