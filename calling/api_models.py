from pydantic import BaseModel, Field


class SessionModel(BaseModel):
    sdp_type: str
    sdp: str


class CallModel(BaseModel):
    call_id: str = Field(alias="id")
    to: str
    event: str
    session: SessionModel


class CallsModel(BaseModel):
    project_uuid: str
    channel_uuid: str
    call: CallModel


__all__ = ("CallsModel",)
