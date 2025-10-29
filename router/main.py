import os

from fastapi import FastAPI, HTTPException, Request

from nexus.event_driven.signals import message_finished, message_started
from nexus.projects.models import Project
from router.entities import DBCon
from router.tasks import start_route
from router.tasks.invoke import start_inline_agents

from .http_bodies import MessageHTTPBody

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


@app.post("/messages")
def messages(request: Request, message: MessageHTTPBody):
    message_started.send(sender=DBCon)

    authenticate(request.query_params.get("token"))

    try:
        project = Project.objects.get(uuid=message.project_uuid)
        print("[+ Message received +]")
        print(message)
        print("[+ ----------------- +]")

        if project.inline_agent_switch:
            print("[+ Starting Inline Agent +]")
            start_inline_agents.delay(message.dict())
        else:
            start_route.delay(message.dict())

    finally:
        message_finished.send(sender=DBCon)
    return {}
