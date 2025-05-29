from typing import Dict, List
from nexus.inline_agents.components import INSTRUCTIONS
import ftfy


class InstructionsUseCase:
    def _fix_instruction_encoding(self, instruction: str) -> str:

        if isinstance(instruction, str):
            return ftfy.fix_text(instruction)

        return instruction

    def handle_instructions(self, instructions: List[str], guardrails: List[str], components: List[Dict]) -> str:
        instructions_guardrails = instructions + guardrails
        for component in components:
            component_instructions = INSTRUCTIONS.get(component.get("type"), [])
            extra_instruction = component.get("instructions")

            if extra_instruction:
                extra_instruction = f"<additional_rules>{extra_instruction}</additional_rules>"
                component_instructions.append(extra_instruction)

            instructions_guardrails += component_instructions

        # Fix encoding issues in instructions
        fixed_instructions = [self._fix_instruction_encoding(instruction) for instruction in instructions_guardrails]
        instructions = "\n".join(fixed_instructions)
        return instructions
