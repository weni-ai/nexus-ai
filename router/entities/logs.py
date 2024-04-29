from dataclasses import dataclass


@dataclass
class ContactMessageDTO:
    contact_urn: str
    text: str
    llm_respose: str
    content_base_uuid: str
    project_uuid: str
