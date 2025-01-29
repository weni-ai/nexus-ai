import json

from pydantic import BaseModel
from typing import Dict, List, Optional, Any


class ContactField(BaseModel):
    key: str
    value: Any


class Message(BaseModel):
    project_uuid: str
    text: str
    contact_urn: str
    metadata: Optional[Dict] = {}
    attachments: Optional[List] = []
    msg_event: Optional[dict] = {}
    contact_fields: List[ContactField] = []

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}

    @property
    def contact_fields_as_json(self) -> str:
        contact_fields = {}

        for field in self.contact_fields:
            contact_fields[field.key] = field.value

        return json.dumps(contact_fields)


def message_factory(*args, contact_fields: dict = {}, **kwargs) -> Message:
    fields = []

    if contact_fields:
        for key, value in contact_fields.items():
            field = ContactField(key=key, value=value.get("value") if value else None)
            fields.append(field)

    return Message(*args, **kwargs, contact_fields=fields)
