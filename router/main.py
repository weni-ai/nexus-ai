
import os
from typing import List
from fastapi import FastAPI, Request, HTTPException
from django.conf import settings
from nexus.event_driven.signals import message_started, message_finished

from router.entities import (
    Message, DBCon
)
from router.tasks import (
    start_route,
    start_multi_agents
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

        multi_agents_projects: List[str] = settings.MULTI_AGENTS_PROJECTS
        print("[+ Message received +]")
        print(message)
        print("[+ ----------------- +]")

        if message.project_uuid in multi_agents_projects:
            print("[+ Starting Agent Builder 2.0 +]")
            start_multi_agents.delay(message.dict())
        else:
            start_route.delay(message.dict())

    finally:
        message_finished.send(sender=DBCon)
    return {}
