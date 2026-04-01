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


def _normalize_preview_contact_urn(contact_urn: str, preview: bool) -> str:
    if not preview or not contact_urn:
        return contact_urn
    # New broadcast can send plain email; preview flows expect ext: URN.
    if "@" in contact_urn and not contact_urn.startswith("ext:"):
        return f"ext:{contact_urn}"
    return contact_urn


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
            preview: bool = bool(message.preview)
            normalized_contact_urn = _normalize_preview_contact_urn(message.contact_urn, preview)
            task_kwargs = {
                "message": message.dict(),
            }
            task_kwargs["message"]["contact_urn"] = normalized_contact_urn
            user_email = normalized_contact_urn.replace("ext:", "").lstrip(":")
            if preview:
                task_kwargs.update(
                    {
                        "preview": True,
                        "user_email": user_email,
                    }
                )
                queue = "celery"

            start_inline_agents.apply_async(kwargs=task_kwargs, queue=queue)
        else:
            start_route.delay(message.dict())

    finally:
        message_finished.send(sender=DBCon)
    return {}
