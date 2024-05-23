
import os

from fastapi import FastAPI, Request, HTTPException

from nexus.event_driven.signals import message_started, message_finished

from router.entities import (
    Message, DBCon
)
from router.tasks import start_route


app = FastAPI()


def authenticate(token: str):
    if not token:
        raise HTTPException(status_code=401, detail="Authentication credentials not provided")

    if os.environ.get("ROUTER_TOKEN") == token:
        return

    raise HTTPException(status_code=403, detail="Wrong credentials")


@app.get("/")
def healthcheck():
    return {}


@app.post('/messages')
def messages(request: Request, message: Message):
    message_started.send(sender=DBCon)

    authenticate(request.query_params.get("token"))

    try:

        print("[+ Mensagem recebida +]")
        print(message)
        print("[+ ----------------- +]")

        start_route.delay(message.dict())

    finally:
        message_finished.send(sender=DBCon)
    return {}
