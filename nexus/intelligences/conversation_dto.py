from dataclasses import dataclass
from django.conf import settings


@dataclass
class ConversationCreationDTO:
    uuid: str
    message: str
    topic: str
    project: str
    csat: str
    created_at: str 

@dataclass
class WindowConversationDTO:
    project_uuid: str
    channel_uuid: str
    start_date: str
    end_date: str
    contact_urn: str
    has_chats_room: bool
    external_id: str

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}