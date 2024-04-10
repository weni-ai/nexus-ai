from pydantic import BaseModel
from typing import Dict, List, Optional
from typing import Optional

class Message(BaseModel):
    project_uuid: str
    text: str
    contact_urn: str
    metadata: Optional[Dict] = {}
    attachments: Optional[List] = []

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}