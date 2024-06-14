import re
from openai import OpenAI

from typing import List

from django.conf import settings

from router.classifiers.interfaces import Classifier

from router.entities.flow import FlowDTO


class ChatGPT_Function_Classifier(Classifier):

    def __init__(
        self,
        api_key: str,
        chatgpt_model: str,
    ):
        self.api_key = api_key
        self.chatgpt_model = chatgpt_model
        self.client = self.get_client()
        self.prompt = settings.CHATGPT_CONTEXT_PROMPT
        self.flow_name_mapping = {}

    def get_client(self):
        return OpenAI(api_key=self.api_key)

    def tools(
        self,
        flows: List[FlowDTO]
    ) -> List[dict]:

        tools = []
        for flow in flows:
            valid_name = re.sub(r'[^a-zA-Z0-9_-]', '_', flow.name)
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

    def predict(
        self,
        message: str,
        flows: List[FlowDTO],
        language: str = "por"
    ) -> str:

        print(f"[+ ChatGPT message function classification: {message} ({language}) +]")
        msg = [
            {
                "role": "system",
                "content": self.prompt
            },
            {
                "role": "user",
                "content": message
            }
        ]

        flows_list = self.tools(flows)

        response = self.client.chat.completions.create(
            model=self.chatgpt_model,
            messages=msg,
            tools=flows_list,
            tool_choice="auto"
        )

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls

        if not tool_calls:
            classification = self.CLASSIFICATION_OTHER
            return classification

        multiple_classifications = []
        for tool_call in tool_calls:
            original_flow_name = self.flow_name_mapping[tool_call.function.name]
            multiple_classifications.append(
                original_flow_name
            )

        return multiple_classifications[0]
