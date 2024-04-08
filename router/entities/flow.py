from dataclasses import dataclass


@dataclass
class FlowDTO:
    uuid: str
    name: str
    prompt: str
    fallback: str
    content_base_uuid: str
