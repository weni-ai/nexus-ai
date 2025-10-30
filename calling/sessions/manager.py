from aiortc import RTCPeerConnection
from aiortc.rtcconfiguration import RTCConfiguration, RTCIceServer

from calling.rtc_config import RTC_CONFIG

from .session import Session


class SessionManager:
    _active_sessions = {}

    @classmethod
    def _add_active_session(cls, session: Session) -> None:
        cls._active_sessions[session.call_id] = session

    @classmethod
    def setup_session(cls, call_id: str, sdp: str) -> Session:
        wpp_connection = RTCPeerConnection(configuration=RTC_CONFIG)
        session = Session(call_id, sdp, wpp_connection)
        cls._add_active_session(session)

        return session

    @classmethod
    def is_session_active(cls, call_id: str) -> bool:
        return call_id in cls._active_sessions

    @classmethod
    def get_session(cls, call_id: str) -> Session | None:
        return cls._active_sessions.get(call_id)

    @classmethod
    async def close_session(cls, call_id: str) -> None:
        session = cls.get_session(call_id)

        if session is not None:
            cls._active_sessions.pop(call_id)
            await session.close()
