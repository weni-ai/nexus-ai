import json
from typing import Dict, List

import sentry_sdk

from nexus.celery import app as celery_app
from nexus.event_domain.event_observer import EventObserver
from nexus.inline_agents.models import InlineAgentMessage
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase


class SaveTracesObserver(EventObserver):
    def perform(
        self,
        trace_events: List[Dict],
        project_uuid: str,
        contact_urn: str,
        agent_response: str,
        preview: bool,
        session_id: str,
        source_type: str,
        contact_name: str,
        channel_uuid: str,
        **kwargs,
    ):
        print("Start SaveTracesObserver")

        data = ""

        for trace_event in trace_events:
            trace_events_json = trace_events_to_json(trace_event)
            data += trace_events_json + "\n"

        save_inline_trace_events.delay(
            trace_events=trace_events,
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            agent_response=agent_response,
            preview=preview,
            session_id=session_id,
            source_type=source_type,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
        )


def trace_events_to_json(trace_event):
    return json.dumps(trace_event, default=str)


@celery_app.task()
def save_inline_trace_events(
    trace_events: List[Dict],
    project_uuid: str,
    contact_urn: str,
    agent_response: str,
    preview: bool,
    session_id: str,
    source_type: str,
    contact_name: str,
    channel_uuid: str,
):
    try:
        message = save_inline_message_to_database(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            text=agent_response,
            preview=preview,
            session_id=session_id,
            source_type=source_type,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
        )

        data = _prepare_trace_data(trace_events)

        filename = f"{message.uuid}.jsonl"
        key = f"inline_traces/{project_uuid}/{filename}"

        upload_traces_to_s3(data, key)

    except Exception as e:
        print(f"Error saving inline trace events: {e}")
        sentry_sdk.set_tag("project_uuid", project_uuid)
        sentry_sdk.set_tag("contact_urn", contact_urn)
        sentry_sdk.set_context(
            "extra_data",
            {
                "agent_response": agent_response,
                "preview": preview,
                "session_id": session_id,
                "source_type": source_type,
                "contact_name": contact_name,
                "channel_uuid": channel_uuid,
            },
        )
        sentry_sdk.set_context("trace_events", trace_events)


def _get_message_service():
    from router.services.message_service import MessageService

    return MessageService()


def save_inline_message_to_database(
    project_uuid: str,
    contact_urn: str,
    text: str,
    preview: bool,
    session_id: str,
    source_type: str,
    contact_name: str,
    channel_uuid: str = None,
) -> InlineAgentMessage:
    message_service = _get_message_service()
    message_service.handle_message_cache(
        contact_urn=contact_urn,
        contact_name=contact_name,
        project_uuid=project_uuid,
        msg_text=text,
        source=source_type,
        channel_uuid=channel_uuid,
        preview=preview,
    )

    source = {True: "preview", False: "router"}

    return InlineAgentMessage.objects.create(
        project_id=project_uuid,
        text=text,
        source=source.get(preview),
        contact_urn=contact_urn,
        session_id=session_id,
        source_type=source_type,
    )


def _prepare_trace_data(trace_events: List[Dict]) -> str:
    data = ""
    for trace_event in trace_events:
        trace_events_json = trace_events_to_json(trace_event)
        data += trace_events_json + "\n"
    return data


def upload_traces_to_s3(data: str, key: str):
    print(f"Uploading traces to s3: {key}")
    BedrockFileDatabase().upload_inline_traces(data, key)
