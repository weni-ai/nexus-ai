import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiortc.contrib.media import MediaStreamTrack
from aiortc.rtcrtpsender import RTCRtpSender

if TYPE_CHECKING:
    from aiortc import RTCPeerConnection

from enum import Enum


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
    agents: dict = None
    openai_datachannel: str = None

    wpp_audio_sender: RTCRtpSender = None
    wpp_audio_track: MediaStreamTrack = None

    input_text: str = ""
    current_task: asyncio.Task = None
    status: Status = Status.WAITING_CONTACT

    def set_agents(self, agents: dict) -> None:
        self.agents = agents

    def set_wpp_audio_track(self, track: MediaStreamTrack) -> None:
        self.wpp_audio_track = track

    def set_answer_sdp(self, sdp: str) -> None:
        self.answer_sdp = sdp

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

    async def close(self) -> None:
        await self.wpp_connection.close()

        if self.openai_connection is not None:
            await self.openai_connection.close()
