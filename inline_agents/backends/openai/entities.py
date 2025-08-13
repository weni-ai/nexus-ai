from dataclasses import dataclass


@dataclass
class Context:
    credentials: dict
    globals: dict
    contact: dict
    project: dict
    content_base: dict