
from typing import List, Dict


from fastapi import FastAPI

from router.repositories.orm import FlowsORMRepository
from router.classifiers.zeroshot import ZeroshotClassifier
from router.classifiers import Classifier
from router.classifiers import classify
from router.entities import FlowDTO, Message, DBCon
from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase

from nexus.event_driven.signals import message_started, message_finished
from nexus.intelligences.llms import ChatGPTClient

app = FastAPI()



def start_flow(flow: FlowDTO, message: Message, params: Dict):
    print(f"[+ Iniciando fluxo para contato {message.contact_urn} +]")
    print(f"[+ Message: {params} +]")


def call_llm(indexer, llm_model, message: Message, fallback_flow: FlowDTO):

    chunks: List[str] = get_chunks(
        indexer,
        text=message.text,
        content_base_uuid=fallback_flow.content_base_uuid
    )

    if not chunks:
        raise Exception  # tratar depois
    
    response = llm_model.request_gpt()
    gpt_message = response.get("answers").get("text")

    params = {
        "gpt_message": gpt_message
    }

    start_flow(fallback_flow, message, params)

def get_chunks(indexer, text: str, content_base_uuid: str) -> List[str]:
    client = indexer
    response = client.search_data(content_base_uuid=content_base_uuid, text=text)
    if response.get("status") == 200:
        texts_chunks: List[str] = response.get("data")
        return texts_chunks


@app.post('/messages')
def messages(message: Message):
    message_started.send(sender=DBCon)
    try:

        print("[+ Mensagem recebida +]")

        flows_repository = FlowsORMRepository()
        flows: List[FlowDTO] = flows_repository.project_flows(message.project_uuid, False)

        classification: str = classify(ZeroshotClassifier(), message.text, flows)

        print(f"[+ Mensagem classificada: {classification} +]")

        if classification == Classifier.CLASSIFICATION_OTHER:
            print(f"[- Fallback -]")
            fallback_flow: FlowDTO = flows_repository.project_flow_fallback(message.project_uuid, True)

            # call_llm(SentenXFileDataBase(), message, fallback_flow)
            call_llm(Indexer(), ChatGPTClient(), message, fallback_flow)

            return {}

        for flow in flows:
            if classification == flow.name:
                print("[+ Fluxo +]")
                start_flow(flow, message, params={"input": message.text})
    finally:
        message_finished.send(sender=DBCon)
    return {}


# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)

class LLM:
    def request_gpt(self):
        return {"answers":[{"text": "Resposta do LLM"}],"id":"0"}

class Indexer:
    def search_data(self, content_base_uuid: str, text: str):
        return {
            "status": 200,
            "data": ["Lorem Ipsum"]
        }