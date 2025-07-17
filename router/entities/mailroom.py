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
        sanitized = ""
        self.sanitize_webchat_urn()
        for char in self.contact_urn:
            if not char.isalnum() and char not in '-_.:':
                sanitized += f"_{ord(char)}"
            else:
                sanitized += char
        return sanitized
    
    def sanitize_webchat_urn(self):
        pattern = r'(:[0-9]+)@'
        match = re.search(pattern, self.contact_urn)
        if match:
            colon_number_end = match.end(1)
            at_position = self.contact_urn.find('@', colon_number_end)
            if at_position != -1:
                self.contact_urn = self.contact_urn[:at_position]


def message_factory(*args, contact_fields: dict = {}, metadata: dict = {}, **kwargs) -> Message:
    fields = []

    if metadata is None:
        metadata = {}

    if contact_fields:
        for key, value in contact_fields.items():
            field = ContactField(key=key, value=value.get("value") if value else None)
            fields.append(field)

    return Message(*args, **kwargs, contact_fields=fields, metadata=metadata)
