from abc import ABC
from typing import Dict


class LLMClient(ABC):

    @classmethod
    def get_by_type(cls, type):
        return filter(lambda llm: llm.code==type, cls.__subclasses__())
    
    def replace_vars(self, prompt: str, replace_variables: Dict) -> str:
        for key in replace_variables.keys():
            replace_str = "{{" + key + "}}"
            prompt = prompt.replace(replace_str, replace_variables.get(key))
        return prompt

    def get_prompt(self, instructions_formatted: str, context: str, agent: Dict, question: str = ""):
        variables = {
            "agent_name": agent.get("name"),
            "agent_role": agent.get("role"),
            "agent_goal": agent.get("goal"),
            "agent_personality": agent.get("personality"),
            "instructions_formatted": instructions_formatted,
            "context": context,
            "question": question,
        }

        if context:
            return self.replace_vars(self.prompt_with_context, variables)
        return self.replace_vars(self.prompt_without_context, variables)

    def request_gpt(self):
        pass
