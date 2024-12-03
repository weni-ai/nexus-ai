from dataclasses import dataclass


@dataclass
class FlowDTO:
    pk: str
    uuid: str
    name: str
    prompt: str
    fallback: str
    content_base_uuid: str
