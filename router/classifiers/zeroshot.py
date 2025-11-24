import logging
from typing import List

from django.conf import settings

from router.classifiers.interfaces import Classifier
from router.clients.zeroshot import NexusZeroshotClient, ZeroshotClient
from router.entities.flow import FlowDTO


class ZeroshotException(Exception):
    pass


class ZeroshotClassifier(Classifier):
    def __init__(
        self, version: str = None, client=NexusZeroshotClient, chatbot_goal: str = settings.DEFAULT_AGENT_GOAL
    ) -> None:
        self.__version = version
        self.chatbot_goal = chatbot_goal
        self.client = client

    def predict(self, message: str, flows: List[FlowDTO], language: str = "por") -> str:
        try:
            logging.getLogger(__name__).info(
                "Zeroshot message classification", extra={"language": language, "message_len": len(message or "")}
            )
            flows_list = []
            for flow in flows:
                flows_list.append(
                    {
                        "class": flow.name,
                        "context": flow.prompt,
                    }
                )
            if not flows_list:
                return self.CLASSIFICATION_OTHER

            response: dict = self.client(self.chatbot_goal).fast_predict(message, flows_list, language)

            if response.get("other"):
                return self.CLASSIFICATION_OTHER

            return response.get("classification")
        except Exception as e:
            message = f"Zeroshot Error: {e}"
            logging.getLogger(__name__).error(message)
            raise ZeroshotException(message) from e


if __name__ == "__main__":  # pragma: no cover
    client = ZeroshotClient()
    client.fast_predict()
