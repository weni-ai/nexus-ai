
from pydantic import BaseModel

from fastapi import FastAPI

from router.repositories.orm import FlowsORMRepository
from router.classifiers.zeroshot import ZeroshotClassifier
from router.classifiers import classify

from nexus.event_driven.signals import message_started, message_finished

app = FastAPI()



class Message(BaseModel):
    project_uuid: str
    text: str
    channel_type: str
    contact_urn: str


@app.post('/messages')
def messages(message: Message):
    message_started.send(sender=message)
    try:
        flows = FlowsORMRepository().project_flows(message.project_uuid)
        print(classify(ZeroshotClassifier(), message.text, flows))
    finally:
        message_finished.send(sender=message)
    return {}



# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)