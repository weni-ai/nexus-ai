import json
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

DEFAULT_IG_RESPONSE_TYPE = "dm_comment"


def extract_ig_comment_broadcast_fields(metadata: Optional[Dict] = None) -> Dict[str, str]:
    """Return ig_comment_id / ig_response_type for Instagram comment replies.

    Mailroom sends the comment under metadata.overwrite_message.ig_comment.
    The outbound broadcast needs those two keys on msg; media is inbound-only.
    """
    if not isinstance(metadata, dict):
        return {}

    overwrite_message = metadata.get("overwrite_message")
    if not isinstance(overwrite_message, dict):
        return {}

    ig_comment = overwrite_message.get("ig_comment")
    if not isinstance(ig_comment, dict):
        return {}

    ig_comment_id = ig_comment.get("id")
    if ig_comment_id is None or ig_comment_id == "":
        return {}

    ig_response_type = (
        overwrite_message.get("ig_response_type") or ig_comment.get("ig_response_type") or DEFAULT_IG_RESPONSE_TYPE
    )
    return {
        "ig_comment_id": str(ig_comment_id),
        "ig_response_type": str(ig_response_type),
    }


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

        pattern = r"(:[0-9]+)@.*"
        match = re.search(pattern, urn_to_sanitize)
        if match:
            urn_to_sanitize = re.sub(pattern, r"\1", urn_to_sanitize)

        sanitized = ""
        for char in urn_to_sanitize:
            if not char.isalnum() and char not in "-_.:":
                sanitized += f"_{ord(char)}"
            else:
                sanitized += char
        return sanitized


def message_factory(*args, contact_fields: Optional[dict] = None, metadata: Optional[dict] = None, **kwargs) -> Message:
    if contact_fields is None:
        contact_fields = {}
    if metadata is None:
        metadata = {}
    fields = []

    if contact_fields:
        for key, value in contact_fields.items():
            field = ContactField(key=key, value=value.get("value") if value else None)
            fields.append(field)

    return Message(*args, **kwargs, contact_fields=fields, metadata=metadata)
