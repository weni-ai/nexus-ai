import logging
import os

from fastapi import FastAPI, HTTPException, Request

from nexus.event_driven.signals import message_finished, message_started
from nexus.projects.models import Project
from router.entities import DBCon
from router.tasks import start_route
from router.tasks.invoke import start_inline_agents

from .http_bodies import MessageHTTPBody

logger = logging.getLogger(__name__)

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
        logger.info(
            f"Message received, from project_uuid: {message.project_uuid}, "
            f"text: {message.text}, contact_urn: {message.contact_urn}"
        )

        if project.inline_agent_switch:
            logger.info("Starting Inline Agent")
            queue = "inline-agents"
            task_kwargs = {
                "message": message.dict(),
            }
            preview: bool = message.preview

            if preview:
                task_kwargs.update(
                    {
                        "preview": True,
                        "user_email": message.contact_urn,
                    }
                )
                queue = "celery"

            start_inline_agents.apply_async(
                kwargs=task_kwargs,
                queue=queue,
            )
        else:
            start_route.delay(message.dict())

    finally:
        message_finished.send(sender=DBCon)
    return {}
