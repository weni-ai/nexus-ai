from dataclasses import dataclass


@dataclass
class FlowDTO:
    name: str
    prompt: str
    pk: str = None
    uuid: str = None
    fallback: str = None
    content_base_uuid: str = None
    send_to_llm: bool = False
