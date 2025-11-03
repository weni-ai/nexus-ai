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
    openai_connection: "RTCPeerConnection" = None
    answer_sdp: str = None
    agents: dict = None
    openai_datachannel: str = None

    def set_agents(self, agents: dict) -> None:
        self.agents = agents

    def set_wpp_audio_track(self, track: MediaStreamTrack) -> None:
        self.wpp_audio_track = track

    def set_answer_sdp(self, sdp: str) -> None:
        self.answer_sdp = sdp

    def set_openai_datachannel(self, datachannel: str) -> None:
        self.openai_datachannel = datachannel

    async def close(self) -> None:
        await self.wpp_connection.close()

        if self.openai_connection is not None:
            await self.openai_connection.close()
