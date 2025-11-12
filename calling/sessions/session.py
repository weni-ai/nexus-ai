import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from aiortc.contrib.media import MediaPlayer, MediaStreamTrack
from aiortc.rtcrtpsender import RTCRtpSender

from agents import Runner
from agents.memory import Session as OpenAISession

from inline_agents.backend import InlineAgentsBackend
from enum import Enum

if TYPE_CHECKING:
    from aiortc import RTCPeerConnection

from agents import Runner
from agents.memory import Session as OpenAISession

from inline_agents.backend import InlineAgentsBackend
from router.entities.mailroom import Message


class Status(Enum):
    WAITING_CONTACT = 0
    WAITING_RESPONSE = 1
    ORCHESTRATION_INTERRUPTED = 2
    RESPONDING = 3


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
    message_obj: Message = None

    wpp_audio_sender: RTCRtpSender = None
    wpp_audio_track: MediaStreamTrack = None
    audio_player: MediaPlayer = None 

    input_text: str = ""
    current_task: asyncio.Task = None
    status: Status = Status.WAITING_CONTACT

    def set_agents(self, agents: dict) -> None:
        self.agents = agents

    def set_wpp_audio_track(self, track: MediaStreamTrack) -> None:
        self.wpp_audio_track = track
    
    def set_message_obj(self, message_obj: Message) -> None:
        self.message_obj = message_obj

    def set_answer_sdp(self, sdp: str) -> None:
        self.answer_sdp = sdp
    
    def set_orchestration_session(self, session: OpenAISession) -> None:
        self.orchestration_session = session

    def set_orchestration_session_id(self, session_id: str) -> None:
        self.orchestration_session_id = session_id

    def set_openai_datachannel(self, datachannel: str) -> None:
        self.openai_datachannel = datachannel
        
    def set_status(self, status: Status):
        if status == Status.RESPONDING:
            self.input_text = ""

        self.status = status

    def has_pending_task(self) -> bool:
        return self.current_task and not self.current_task.done()

    def interrupt_response(self, input_text: str):
        self.input_text += "\n" + input_text
        self.set_status(Status.ORCHESTRATION_INTERRUPTED)
        
        if self.has_pending_task:
            self.current_task.cancel()
    
    def set_orchestration_client(self, client) -> None:
        self.orchestration_client = client
    
    def set_backend(self, backend: InlineAgentsBackend) -> None:
        self.backend = backend

    async def close(self) -> None:
        await self.wpp_connection.close()

        if self.openai_connection is not None:
            await self.openai_connection.close()
