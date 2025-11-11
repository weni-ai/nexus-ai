from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from aiortc.contrib.media import MediaStreamTrack

if TYPE_CHECKING:
    from aiortc import RTCPeerConnection

from agents import Runner
from agents.memory import Session as OpenAISession

from inline_agents.backend import InlineAgentsBackend


@dataclass
class Session:
    call_id: str
    offer_sdp: str
    wpp_connection: "RTCPeerConnection"
    openai_connection: "RTCPeerConnection" = None
    answer_sdp: str = None
    agents: Optional[dict] = None
    openai_datachannel: str = None
    orchestration_client: Runner = None
    orchestration_backend: InlineAgentsBackend = None
    orchestration_session: OpenAISession = None
    orchestration_session_id: str = None
    started_human_support: bool = False

    def set_agents(self, agents: dict) -> None:
        self.agents = agents

    def set_wpp_audio_track(self, track: MediaStreamTrack) -> None:
        self.wpp_audio_track = track

    def set_answer_sdp(self, sdp: str) -> None:
        self.answer_sdp = sdp
    
    def set_orchestration_session(self, session: OpenAISession) -> None:
        self.orchestration_session = session

    def set_orchestration_session_id(self, session_id: str) -> None:
        self.orchestration_session_id = session_id

    def set_openai_datachannel(self, datachannel: str) -> None:
        self.openai_datachannel = datachannel
    
    def set_orchestration_client(self, client) -> None:
        self.orchestration_client = client
    
    def set_backend(self, backend: InlineAgentsBackend) -> None:
        self.backend = backend

    async def close(self) -> None:
        await self.wpp_connection.close()

        if self.openai_connection is not None:
            await self.openai_connection.close()
