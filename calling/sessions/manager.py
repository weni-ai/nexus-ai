from aiortc import RTCPeerConnection
from aiortc.rtcconfiguration import RTCConfiguration, RTCIceServer

from .session import Session


class SessionManager:
    _active_sessions = {}

    @classmethod
    def _add_active_session(cls, session: Session) -> None:
        cls._active_sessions[session.call_id] = session

    @classmethod
    def setup_session(cls, call_id: str, phone_number_id: str, project_uuid: str, contact_urn: str, offer_sdp: str = None,) -> Session:
        wpp_connection = RTCPeerConnection()
        session = Session(phone_number_id, wpp_connection, project_uuid, contact_urn, call_id=call_id, offer_sdp=offer_sdp)
        cls._add_active_session(session)

        return session

    @classmethod
    def setup_business_initiated_session(cls, phone_number_id: str, project_uuid: str, contact_urn: str) -> Session:
        wpp_connection = RTCPeerConnection()
        session = Session(phone_number_id, wpp_connection, project_uuid, contact_urn)

        return session

    @classmethod
    def is_session_active(cls, call_id: str) -> bool:
        return call_id in cls._active_sessions

    @classmethod
    def get_session(cls, call_id: str) -> Session | None:
        return cls._active_sessions.get(call_id)

    @classmethod
    async def close_session(cls, call_id: str, session: Session = None) -> None:
        if session is None:
            session = cls.get_session(call_id)

        if session is not None:
            cls._active_sessions.pop(call_id)
            if session.orchestration_session is not None:
                session.orchestration_session.clear_session()

            await session.close()
