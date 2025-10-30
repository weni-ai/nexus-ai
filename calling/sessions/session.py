from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiortc.contrib.media import MediaStreamTrack

if TYPE_CHECKING:
    from aiortc import RTCPeerConnection


@dataclass
class Session:
    call_id: str
    offer_sdp: str
    wpp_connection: "RTCPeerConnection"
    agents: dict = None
    openai_connection: "RTCPeerConnection" = None

    def set_agents(self, agents: dict):
        self.agents = agents

    def set_wpp_audio_track(self, track: MediaStreamTrack):
        self.wpp_audio_track = track

    async def close(self):
        await self.wpp_connection.close()

        if self.openai_connection is not None:
            await self.openai_connection.close()
