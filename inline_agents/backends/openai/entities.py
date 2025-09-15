from dataclasses import dataclass
from agents import Session
from inline_agents.backends.openai.hooks import HooksState


@dataclass
class Context:
    input_text: str
    credentials: dict
    globals: dict
    contact: dict
    project: dict
    content_base: dict
    session: Session
    hooks_state: HooksState
