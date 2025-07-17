import json
import re
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
    channel_uuid: Optional[str] = None
    contact_name: Optional[str] = None

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}

    @property
    def contact_fields_as_json(self) -> str:
        contact_fields = {}

        for field in self.contact_fields:
            contact_fields[field.key] = field.value

        return json.dumps(contact_fields)

    @property
    def sanitized_urn(self):
        urn_to_sanitize = self.contact_urn

        pattern = r'(:[0-9]+)@.*'
        match = re.search(pattern, urn_to_sanitize)
        if match:
            urn_to_sanitize = re.sub(pattern, r'\1', urn_to_sanitize)

        sanitized = ""
        for char in urn_to_sanitize:
            if not char.isalnum() and char not in '-_.:':
                sanitized += f"_{ord(char)}"
            else:
                sanitized += char
        return sanitized


def message_factory(*args, contact_fields: dict = {}, metadata: dict = {}, **kwargs) -> Message:
    fields = []

    if metadata is None:
        metadata = {}

    if contact_fields:
        for key, value in contact_fields.items():
            field = ContactField(key=key, value=value.get("value") if value else None)
            fields.append(field)

    return Message(*args, **kwargs, contact_fields=fields, metadata=metadata)
