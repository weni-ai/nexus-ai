import os

from django.conf import settings

from inline_agents.backends.openai.grpc import is_grpc_enabled
from nexus.usecases.intelligences.retrieve import get_file_info
from router.clients.flows.http.flow_start import FlowStartHTTPClient
from router.clients.flows.http.send_message import (
    SendMessageHTTPClient,
    WhatsAppBroadcastHTTPClient,
)
from router.clients.preview.simulator.broadcast import SimulateBroadcast, SimulateWhatsAppBroadcastHTTPClient
from router.clients.preview.simulator.flow_start import SimulateFlowStart


def get_action_clients(
    preview: bool = False,
    multi_agents: bool = False,
    project_use_components: bool = False,
    project_uuid: str = None,
):
    if preview:
        flow_start = SimulateFlowStart(os.environ.get("FLOWS_REST_ENDPOINT"), os.environ.get("FLOWS_INTERNAL_TOKEN"))
        if project_use_components:
            broadcast = SimulateWhatsAppBroadcastHTTPClient(
                os.environ.get("FLOWS_REST_ENDPOINT"), os.environ.get("FLOWS_INTERNAL_TOKEN")
            )
        else:
            broadcast = SimulateBroadcast(
                os.environ.get("FLOWS_REST_ENDPOINT"), os.environ.get("FLOWS_INTERNAL_TOKEN"), get_file_info
            )
        return broadcast, flow_start

    # Check if GRPC is enabled for this project (includes use_components validation)
    use_grpc = bool(project_uuid and is_grpc_enabled(project_uuid, use_components=project_use_components))

    if multi_agents and settings.AGENT_USE_COMPONENTS or project_use_components:
        broadcast = WhatsAppBroadcastHTTPClient(
            os.environ.get("FLOWS_REST_ENDPOINT"),
            os.environ.get("FLOWS_SEND_MESSAGE_INTERNAL_TOKEN"),
            use_grpc=use_grpc,
        )
    else:
        broadcast = SendMessageHTTPClient(
            os.environ.get("FLOWS_REST_ENDPOINT"), os.environ.get("FLOWS_SEND_MESSAGE_INTERNAL_TOKEN")
        )

    flow_start = FlowStartHTTPClient(os.environ.get("FLOWS_REST_ENDPOINT"), os.environ.get("FLOWS_INTERNAL_TOKEN"))
    return broadcast, flow_start
