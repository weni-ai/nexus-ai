import asyncio
import time

from aiortc.contrib.media import MediaPlayer

from calling.events.listener import EventListener
from calling.sessions.session import Session

audio_file = "calling/sounds/waiting_sound.mp3"

_global_player = None

def get_audio_track():
    global _global_player
    if _global_player is None:
        _global_player = MediaPlayer(audio_file, loop=True)
    return _global_player.audio


class PlayAudioListener(EventListener):
    async def perform(self, _, session: Session, **kwargs):
        wpp_audio_sender = session.wpp_audio_sender

        if wpp_audio_sender is not None:
            player = MediaPlayer(audio_file, loop=True)
            outgoing_track = player.audio

            await asyncio.sleep(0.01)

            session.set_wpp_audio_track(wpp_audio_sender.track)

            print("Iniciando Musica")
            wpp_audio_sender.replaceTrack(outgoing_track)
