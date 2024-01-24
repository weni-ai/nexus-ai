from dataclasses import dataclass

@dataclass
class ContentBaseFileDTO:
    file: bytes
    extension_file: str
    user_email: str
    content_base_uuid: str
    file_url: str = None
    file_name: str = None


@dataclass
class UpdateContentBaseFileDTO:
    file: bytes = None
    extension_file: str = None
    user_email: str = None
    content_base_uuid: str = None
    file_url: str = None
    file_name: str = None

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}


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