from dataclasses import dataclass

@dataclass
class ContentBaseFileDTO:
    file: bytes
    file_url: str
    extension_file: str
    user_email: str
    content_base_uuid: str
    file_name: str


@dataclass
class ContentBaseTextDTO:
    file: str
    file_name: str
    text: str
    content_base_uuid: str
    user_email: str


@dataclass
class ContentBaseDTO:
    uuid: str
    title: str
    intelligence_uuid: str
    created_at: str = None
    created_by_email: str = None
    modified_by_email: str = None
    modified_at: str = None
