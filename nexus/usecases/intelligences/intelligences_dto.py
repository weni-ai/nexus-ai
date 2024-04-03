from dataclasses import dataclass
from typing import List
from django.conf import settings


@dataclass
class ContentBaseFileDTO:
    file: bytes
    extension_file: str
    user_email: str
    content_base_uuid: str
    file_url: str = None
    file_name: str = None
    uuid: str = None


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
class UpdateLLMDTO:
    project_uuid: str = None
    user_email: str = None
    model: str = None
    setup: dict = None
    advanced_options: dict = None

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}


@dataclass
class ContentBaseTextDTO:
    text: str
    content_base_uuid: str
    user_email: str
    file: str = None
    file_name: str = None


@dataclass
class ContentBaseDTO:
    uuid: str
    title: str
    intelligence_uuid: str
    created_at: str = None
    created_by_email: str = None
    modified_by_email: str = None
    modified_at: str = None

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}


@dataclass
class ContentBaseLogsDTO:
    content_base_uuid: str
    question: str
    language: str
    texts_chunks: List
    full_prompt: str
    weni_gpt_response: str
    testing: bool = False


@dataclass
class ContentBaseLinkDTO:
    link: str
    user_email: str
    content_base_uuid: str
    uuid: str = None


@dataclass
class LLMDTO:
    user_email: str
    project_uuid: str
    setup: dict
    advanced_options: dict = None
    model: str = "WeniGPT"
