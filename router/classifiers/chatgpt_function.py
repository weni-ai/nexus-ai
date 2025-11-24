import logging
import re
from typing import Dict, List

from django.conf import settings
from openai import OpenAI

from router.classifiers.interfaces import Classifier, OpenAIClientInterface
from router.entities.flow import FlowDTO


class OpenAIClient(OpenAIClientInterface):  # pragma: no cover
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = OpenAI(api_key=self.api_key)

    def chat_completions_create(self, model, messages, tools, tool_choice="auto"):
        return self.client.chat.completions.create(model=model, messages=messages, tools=tools, tool_choice=tool_choice)


class ChatGPTFunctionClassifier(Classifier):
    def __init__(
        self,
        agent_goal: str,
        client: OpenAIClientInterface = None,
        chatgpt_model: str = settings.FUNCTION_CALLING_CHATGPT_MODEL,
    ):
        if client is None:
            client = OpenAIClient(settings.OPENAI_API_KEY)
        self.chatgpt_model = chatgpt_model
        self.client = client
        self.prompt = settings.FUNCTION_CALLING_CHATGPT_PROMPT
        self.flow_name_mapping = {}
        self.agent_goal = agent_goal

    def replace_vars(self, prompt: str, replace_variables: Dict) -> str:
        for key in replace_variables.keys():
            replace_str = "{{" + key + "}}"
            value = replace_variables.get(key)
            if not isinstance(value, str):
                value = str(value)
            prompt = prompt.replace(replace_str, value)
        return prompt

    def get_prompt(self):
        variable = {
            "agent_goal": "".join(self.agent_goal),
        }

        return self.replace_vars(prompt=self.prompt, replace_variables=variable)

    def tools(self, flows: List[FlowDTO]) -> List[dict]:
        tools = []
        for flow in flows:
            valid_name = re.sub(r"[^a-zA-Z0-9_-]", "_", flow.name)
            self.flow_name_mapping[valid_name] = flow.name
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": valid_name,
                        "description": flow.prompt,
                    },
                }
            )
        return tools

    def predict(self, message: str, flows: List[FlowDTO], language: str = "por") -> str:
        logging.getLogger(__name__).info(
            "ChatGPT message function classification", extra={"language": language, "message_len": len(message or "")}
        )

        formated_prompt = self.get_prompt()

        msg = [{"role": "system", "content": formated_prompt}, {"role": "user", "content": message}]

        flows_list = self.tools(flows)
        if not flows_list:
            classification = self.CLASSIFICATION_OTHER
            return classification

        response = self.client.chat_completions_create(
            model=self.chatgpt_model, messages=msg, tools=flows_list, tool_choice="auto"
        )

        tool_calls = response.choices[0].message.tool_calls

        if not tool_calls:
            classification = self.CLASSIFICATION_OTHER
            return classification

        multiple_classifications = []
        for tool_call in tool_calls:
            original_flow_name = self.flow_name_mapping[tool_call.function.name]
            multiple_classifications.append(original_flow_name)

        return multiple_classifications[0]
