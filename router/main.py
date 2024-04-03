
from typing import List, Dict


from fastapi import FastAPI

from router.repositories.orm import FlowsORMRepository
from router.classifiers.zeroshot import ZeroshotClassifier
from router.classifiers import Classifier
from router.classifiers import classify
from router.entities import FlowDTO, Message

from nexus.event_driven.signals import message_started, message_finished

app = FastAPI()


class DBCon:
    pass


def start_flow(flow: FlowDTO, message: Message, params: Dict):
    print(f"[+ Iniciando fluxo para contato {message.contact_urn} +]")
    print(f"[+ Message: {params} +]")


def call_llm(message: Message, fallback_flow: FlowDTO):
    print("[+ Chamando LLM +]")
    chunks: List[str] = get_chunks(
        text=message.text,
        content_base_uuid=fallback_flow.content_base_uuid
    )

    if not chunks:
        raise Exception  # tratar depois


from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase

def get_chunks(text: str, content_base_uuid: str) -> List[str]:
    client = SentenXFileDataBase()
    response = client.search_data(content_base_uuid=content_base_uuid, text=text)
    if response.get("status_code") == 200:
        texts_chunks: List[str] = response.get("data")
        return texts_chunks


@app.post('/messages')
def messages(message: Message):
    message_started.send(sender=DBCon)
    try:
        flows_repository = FlowsORMRepository()
        flows: List[FlowDTO] = flows_repository.project_flows(message.project_uuid, False)

        classification: str = classify(ZeroshotClassifier(), message.text, flows)
        print(f"[CLASSIFICOU {classification}]")

        if classification == Classifier.CLASSIFICATION_OTHER:

            print("[+] Fallback [+]")
            fallback_flow: FlowDTO = flows_repository.project_flow_fallback(message.project_uuid, True)

            call_llm(message, fallback_flow)

            return {}

        for flow in flows:
            if classification == flow.name:
                start_flow(flow, message, params={"input": message.text})
    finally:
        message_finished.send(sender=DBCon)
    print("------------------------------")
    return {}



# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)