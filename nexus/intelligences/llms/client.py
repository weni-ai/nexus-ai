from abc import ABC
from typing import Dict, List

from openai import OpenAI

from router.entities import LLMSetupDTO, ContactMessageDTO

from django.conf import settings


class LLMClient(ABC):  # pragma: no cover

    @classmethod
    def get_by_type(cls, type):
        return filter(lambda llm: llm.code == type, cls.__subclasses__())

    def get_client(self):
        return OpenAI(api_key=self.api_key)

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
        }

        if question:
            variables.update({"question": question})

        if context:
            return self.replace_vars(self.prompt_with_context, variables)
        return self.replace_vars(self.prompt_without_context, variables)

    def request_gpt(self, instructions: List, chunks: List, agent: Dict, question: str, llm_config: LLMSetupDTO, last_messages: List[ContactMessageDTO]):
        pass

    def format_few_shot(self, few_shot: str) -> List[Dict]:
        return list(eval(few_shot))

    def format_post_prompt(self, question: str) -> str:
        return self.post_prompt.replace("{{question}}", question)

    def chat_completion(self, instructions: List, chunks: List, agent: Dict, question: str, llm_config: LLMSetupDTO, last_messages: List[ContactMessageDTO], few_shot: str = None):
        self.prompt = self.format_prompt(instructions, chunks, agent)

        kwargs = dict(
            temperature=float(llm_config.temperature) if llm_config.temperature else None,
            top_p=float(llm_config.top_p) if llm_config.top_p else None,
            max_tokens=int(llm_config.max_tokens) if llm_config.max_tokens else None
        )

        if settings.TOKEN_LIMIT:  # TODO: remove token limit
            kwargs.update({"max_tokens": settings.TOKEN_LIMIT})

        messages = [
            {
                "role": "system",
                "content": self.prompt
            }
        ]

        if few_shot:
            messages += self.format_few_shot(few_shot)

        if last_messages:
            for last_message in last_messages:
                messages.append(
                    {
                        "role": "user",
                        "content": last_message.text
                    }
                )
                messages.append(
                    {
                        "role": "assistant",
                        "content": last_message.llm_respose
                    }
                )

        post_prompt = self.format_post_prompt(question)

        messages.append(
            {
                "role": "user",
                "content": post_prompt,
            }
        )

        chat_completion = self.client.chat.completions.create(
            messages=messages,
            model=llm_config.model_version,
            **{k: v for k, v in kwargs.items() if v is not None}
        )

        text_answers = chat_completion.choices[0].message.content

        return {
            "answers": [
                {
                    "text": text_answers
                }
            ],
            "id": "0"
        }
