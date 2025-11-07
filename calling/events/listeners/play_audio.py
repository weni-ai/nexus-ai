from aiortc.contrib.media import MediaPlayer

from calling.events.listener import EventListener
from calling.sessions.session import Session

audio_file = "calling/sounds/waiting_sound.mp3"


class PlayAudioListener(EventListener):
    async def perform(self, _, session: Session, **kwargs):
        player = MediaPlayer(audio_file)
        outgoing_track = player.audio

        wpp_audio_sender = session.wpp_audio_sender

        if wpp_audio_sender is not None:
            session.set_wpp_audio_track(wpp_audio_sender.track)
            wpp_audio_sender.replaceTrack(outgoing_track)
