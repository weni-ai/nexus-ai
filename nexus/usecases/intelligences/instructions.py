from typing import List, Optional

from django.conf import settings

from nexus.intelligences.models import ContentBase


def resolve_retail_instructions(request_instructions: Optional[List[str]]) -> List[str]:
    if request_instructions is not None:
        return request_instructions
    return settings.DEFAULT_RETAIL_INSTRUCTIONS


def build_instruction_create_payload(instructions: List[str]) -> List[dict]:
    return [{"instruction": instruction} for instruction in instructions]


def build_initial_retail_instruction_payload(
    content_base: ContentBase,
    request_instructions: Optional[List[str]],
) -> List[dict]:
    if content_base.instructions.exists():
        return []

    instructions = resolve_retail_instructions(request_instructions)
    return build_instruction_create_payload(instructions)
