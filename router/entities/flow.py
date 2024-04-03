from dataclasses import dataclass


@dataclass
class FlowDTO:
    uuid: str
    name: str
    prompt: str
