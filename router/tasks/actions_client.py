import os

from django.conf import settings

from inline_agents.backends.openai.grpc import is_grpc_enabled
from router.clients.flows.http.flow_start import FlowStartHTTPClient
from router.clients.flows.http.send_message import (
    SendMessageHTTPClient,
    WhatsAppBroadcastHTTPClient,
)


def get_action_clients(
    multi_agents: bool = False,
    project_use_components: bool = False,
    project_uuid: str = None,
    stream_support: bool = False,
):
    """Return real Flows HTTP clients. Simulator traffic uses the same clients as production."""

    # GRPC is enabled for multi_agents when: project in list, use_components=False, stream_support=True
    use_grpc = bool(
        multi_agents and project_uuid and is_grpc_enabled(project_uuid, project_use_components, stream_support)
    )

    if multi_agents and settings.AGENT_USE_COMPONENTS or project_use_components:
        broadcast = WhatsAppBroadcastHTTPClient(
            os.environ.get("FLOWS_REST_ENDPOINT"),
            os.environ.get("FLOWS_SEND_MESSAGE_INTERNAL_TOKEN"),
        )
    else:
        broadcast = SendMessageHTTPClient(
            os.environ.get("FLOWS_REST_ENDPOINT"),
            os.environ.get("FLOWS_SEND_MESSAGE_INTERNAL_TOKEN"),
            use_grpc=use_grpc,
        )

    flow_start = FlowStartHTTPClient(os.environ.get("FLOWS_REST_ENDPOINT"), os.environ.get("FLOWS_INTERNAL_TOKEN"))
    return broadcast, flow_start
