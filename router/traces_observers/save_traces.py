import json
from typing import List, Dict

from nexus.celery import app as celery_app
from nexus.inline_agents.models import InlineAgentMessage
from nexus.event_domain.event_observer import EventObserver
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
        **kwargs
    ):
        print("Start SaveTracesObserver")

        data = ""

        for trace_event in trace_events:
            trace_events_json = trace_events_to_json(trace_event)
            data += trace_events_json + '\n'

        save_inline_trace_events.delay(
            trace_events=trace_events,
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            agent_response=agent_response,
            preview=preview,
            session_id=session_id,
            source_type=source_type
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
    source_type: str
):
    message = save_inline_message_to_database(
        project_uuid=project_uuid,
        contact_urn=contact_urn,
        text=agent_response,
        preview=preview,
        session_id=session_id,
        source_type=source_type
    )

    data = _prepare_trace_data(trace_events)

    filename = f"{message.uuid}.json"
    key = f"inline_traces/{project_uuid}/{filename}"

    upload_traces_to_s3(data, key)


def save_inline_message_to_database(
    project_uuid: str,
    contact_urn: str,
    text: str,
    preview: bool,
    session_id: str,
    source_type: str
) -> InlineAgentMessage:
    source = {
        True: "preview",
        False: "router"
    }

    return InlineAgentMessage.objects.create(
        project_id=project_uuid,
        text=text,
        source=source.get(preview),
        contact_urn=contact_urn,
        session_id=session_id,
        source_type=source_type
    )


def _prepare_trace_data(trace_events: List[Dict]) -> str:
    data = ""
    for trace_event in trace_events:
        trace_events_json = trace_events_to_json(trace_event)
        data += trace_events_json + '\n'
    return data


def upload_traces_to_s3(data: str, key: str):
    print(f"Uploading traces to s3: {key}")
    BedrockFileDatabase().upload_inline_traces(data, key)
