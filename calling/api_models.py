from pydantic import BaseModel, Field


class SessionModel(BaseModel):
    sdp_type: str
    sdp: str


class CallModel(BaseModel):
    call_id: str = Field(alias="id")
    to: str
    from_number: str = Field(alias="from")
    event: str
    session: SessionModel


class CallsModel(BaseModel):
    project_uuid: str
    channel_uuid: str
    call: CallModel
    phone_number_id: str
    name: str


__all__ = ("CallsModel",)


class BusinessInitiatedCallsModel(BaseModel):
    project_uuid: str
    contact_urn: str
