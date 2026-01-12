from typing import Dict, List, Optional

from pydantic import BaseModel


class MessageHTTPBody(BaseModel):
    project_uuid: str
    text: str
    contact_urn: str
    channel_uuid: Optional[str] = None
    channel_type: Optional[str] = None
    contact_name: Optional[str] = None
    metadata: Optional[Dict] = {}
    attachments: Optional[List] = []
    msg_event: Optional[dict] = {}
    contact_fields: Optional[dict] = {}

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}
