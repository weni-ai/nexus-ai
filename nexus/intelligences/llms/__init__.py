from typing import Dict

from nexus.intelligences.llms.chatgpt import ChatGPTClient
from nexus.intelligences.llms.wenigpt import WeniGPTClient
from nexus.intelligences.llms.wenigpt_beta import WeniGPTBetaClient
from nexus.intelligences.llms.client import LLMClient


LLM_CLIENTS = {
    "chatgpt": ChatGPTClient,
    "wenigpt": WeniGPTClient,
    "wenigpt_beta": WeniGPTBetaClient,
}


def get_llm_client_by_type(type: str, llm_types: Dict = LLM_CLIENTS) -> LLMClient:
    return llm_types.get(type)
