
import os

from fastapi import FastAPI, Request, HTTPException

from nexus.event_driven.signals import message_started, message_finished

from router.entities import (
    Message, DBCon
)
from router.tasks import (
    start_agent_builder,
    start_route
)

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

        print("[+ Message Received +]")
        print(message)
        print("[+ ----------------- +]")

        agent_builder_2_projects: list = os.environ.get("AGENT_BUILDER_2_PROJECTS")

        if message.project_uuid in agent_builder_2_projects:
            print("[+ Starting Agent Builder 2.0 +]")
            start_agent_builder.delay(message.dict())
        else:
            start_route.delay(message.dict())

    finally:
        message_finished.send(sender=DBCon)
    return {}
