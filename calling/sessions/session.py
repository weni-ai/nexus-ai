import json
import time
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
from calling.agent import rational_instructions


class Status(Enum):
    WAITING_CONTACT = 0
    WAITING_RESPONSE = 1
    ORCHESTRATION_INTERRUPTED = 2
    RESPONDING = 3


@dataclass
class Response:
    MIN_RESPONSE_TIME = 7

    session: "Session"

    awaiting_orchestration: bool = False
    openai_responding: bool = False
    last_resposne: float = None

    def _dc_send_json(self, data: dict) -> None:
        if getattr(self.session.openai_datachannel, "readyState", None) == "open":
            self.session.openai_datachannel.send(json.dumps(data))

    def send(self, data: dict) -> None:
        pass

    def send_rational(self) -> None:
        print("Tentando enviar o Racional")
        if not self.can_send_response():
            return

        data = {
            "type": "response.create",
            "response": {
                "conversation": "none",
                "instructions": rational_instructions.format(response="Aguarde só um momeno, estou trabalhando em sua solicitação"),
            }
        }
        self._dc_send_json(data)

        self.last_resposne = time.time()

    def can_send_response(self) -> bool:
        if self.last_resposne is None:
            return True

        delta = time.time() - self.last_resposne

        return delta > self.MIN_RESPONSE_TIME


@dataclass
class Session:
    call_id: str
    offer_sdp: str
    wa_phone_number_id: str
    wpp_connection: "RTCPeerConnection"
    project_uuid: str
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
    audio_player_track: MediaStreamTrack = None

    input_text: str = ""
    status: Status = Status.WAITING_CONTACT

    current_task: asyncio.Task = None

    response: Response = None

    def __post_init__(self):
        self.response = Response(self)

        # self.rational_task = asyncio.create_task(self.proccess_rational())

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

    # async def proccess_rational(self):
    #     while True:
    #         await asyncio.sleep(10)
            
