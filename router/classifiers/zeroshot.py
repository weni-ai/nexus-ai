from typing import List

from router.classifiers.interfaces import Classifier
from router.clients.zeroshot import ZeroshotClient

from router.entities.flow import FlowDTO

class ZeroshotClassifier(Classifier):

    def __init__(self, version: str = None) -> None:
        self.__version = version

    def predict(self, message: str, flows: List[FlowDTO], language: str = "por") -> str:
        flows_list = []
        for flow in flows:
            flows_list.append(
                {
                    "class": flow.name,
                    "context": flow.prompt,
                }
            )

        response: dict = ZeroshotClient().fast_predict(message, flows_list, language)

        print("25 ", response)

        if response.get("other"):
            return self.CLASSIFICATION_OTHER

        return response.get("classification")



if __name__ == "__main__":
    client = ZeroshotClient()
    client.fast_predict()