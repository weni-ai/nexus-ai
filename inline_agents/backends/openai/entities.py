from dataclasses import dataclass
from agents import Session


@dataclass
class Context:
    input_text: str
    credentials: dict
    globals: dict
    contact: dict
    project: dict
    content_base: dict
    session: Session