from pydantic import BaseModel


class Message(BaseModel):
    project_uuid: str
    text: str
    contact_urn: str
