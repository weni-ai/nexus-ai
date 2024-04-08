
import os
from typing import List, Dict

from fastapi import FastAPI

from router.repositories.orm import FlowsORMRepository, ContentBaseORMRepository
from router.repositories import Repository
from router.classifiers.zeroshot import ZeroshotClassifier
from router.classifiers import Classifier
from router.classifiers import classify
from router.entities import (
    FlowDTO, Message, DBCon, AgentDTO, InstructionDTO, ContentBaseDTO
)
from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase

from nexus.event_driven.signals import message_started, message_finished

from router.direct_message import DirectMessage
from router.flow_start import FlowStart
from nexus.intelligences.llms.client import LLMClient

from router.tasks import start_route


app = FastAPI()


@app.post('/messages')
def messages(message: Message):
    message_started.send(sender=DBCon)
    try:

        print("[+ Mensagem recebida +]")

        start_route.delay(message.dict())

    finally:
        message_finished.send(sender=DBCon)
    return {}


