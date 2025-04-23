from typing import Dict, List
from nexus.inline_agents.components import INSTRUCTIONS


class InstructionsUseCase:
    def handle_instructions(self, instructions: List[str], guardrails: List[str], components: List[Dict]) -> str:
        instructions_guardrails = instructions + guardrails
        for component in components:
            component_instructions = INSTRUCTIONS.get(component.get("type"), [])
            extra_instruction = component.get("instructions")

            if extra_instruction:
                extra_instruction = f"<additional_rules>{extra_instruction}</additional_rules>"
                component_instructions.append(extra_instruction)

            instructions_guardrails += component_instructions
        instructions = "\n".join(instructions_guardrails)
        return instructions
