from nexus.users.models import User
from dataclasses import dataclass

@dataclass
class ContentBaseDTO:
    title: str
    created_by: User

@dataclass
class ContentBaseFileDTO:
    file: bytes
    file_url: str
    extension_file: str
    user_email: str
    content_base_uuid: str