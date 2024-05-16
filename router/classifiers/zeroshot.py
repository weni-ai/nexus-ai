from typing import List

from router.classifiers.interfaces import Classifier
from router.clients.zeroshot import ZeroshotClient

from router.entities.flow import FlowDTO

from django.conf import settings


class ZeroshotClassifier(Classifier):

    def __init__(self, version: str = None, chatbot_goal: str = settings.DEFAULT_AGENT_GOAL) -> None:
        self.__version = version
        self.chatbot_goal = chatbot_goal

    def predict(self, message: str, flows: List[FlowDTO], language: str = "por") -> str:
        print(f"+ Zeroshot message classification: {message} ({language}) +")
        flows_list = []
        for flow in flows:
            flows_list.append(
                {
                    "class": flow.name,
                    "context": flow.prompt,
                }
            )

        response: dict = ZeroshotClient(self.chatbot_goal).fast_predict(message, flows_list, language)

        if response.get("other"):
            return self.CLASSIFICATION_OTHER

        return response.get("classification")

if __name__ == "__main__":
    client = ZeroshotClient()
    client.fast_predict()
