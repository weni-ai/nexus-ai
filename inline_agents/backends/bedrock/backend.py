import boto3

from inline_agents.backend import InlineAgentsBackend
from nexus.environment import env

from .adapter import BedrockTeamAdapter
from nexus.inline_agents.backends.bedrock.repository import BedrockSupervisorRepository
from nexus.events import event_manager
from nexus.projects.websockets.consumers import send_preview_message_to_websocket

from django.template.defaultfilters import slugify


class BedrockBackend(InlineAgentsBackend):
    supervisor_repository = BedrockSupervisorRepository
    team_adapter = BedrockTeamAdapter

    REGION_NAME = env.str('AWS_BEDROCK_REGION_NAME')

    def __init__(self, event_manager_notify=event_manager.notify):
        self.event_manager_notify = event_manager_notify

    def _get_client(self):
        return boto3.client('bedrock-agent-runtime', region_name=self.REGION_NAME)

    def invoke_agents(
        self,
        team: dict,
        input_text: str,
        contact_urn: str,
        project_uuid: str,
        sanitized_urn: str,
        preview: bool = False,
        rationale_switch: bool = False,
        language: str = "en",
        user_email: str = None
    ):
        supervisor = self.supervisor_repository.get_supervisor(project_uuid=project_uuid)

        external_team = self.team_adapter.to_external(
            supervisor=supervisor,
            agents=team,
            input_text=input_text,
            contact_urn=contact_urn,
            project_uuid=project_uuid
        )
        client = self._get_client()

        # Generate a session ID for websocket communication
        session_id = f"project-{project_uuid}-session-{sanitized_urn}"
        session_id = slugify(session_id)

        # Send initial status message if in preview mode and user_email is provided
        if preview and user_email:
            send_preview_message_to_websocket(
                project_uuid=str(project_uuid),
                user_email=user_email,
                message_data={
                    "type": "status",
                    "content": "Starting Bedrock agent processing",
                    "session_id": session_id
                }
            )

        response = client.invoke_inline_agent(**external_team)

        completion = response["completion"]
        full_response = ""
        trace_events = []

        for event in completion:
            if 'chunk' in event:
                chunk = event['chunk']['bytes'].decode()
                full_response += chunk

                # Send chunk through WebSocket if in preview mode and user_email is provided
                if preview and user_email:
                    send_preview_message_to_websocket(
                        project_uuid=str(project_uuid),
                        user_email=user_email,
                        message_data={
                            "type": "chunk",
                            "content": chunk,
                            "session_id": session_id
                        }
                    )

            if 'trace' in event:
                # Store the trace event for potential use
                trace_data = event['trace']
                trace_events.append(trace_data)

                # Notify observers about the trace
                self.event_manager_notify(
                    event="inline_trace_observers",
                    inline_traces=trace_data,
                    user_input=input_text,
                    contact_urn=contact_urn,
                    project_uuid=project_uuid,
                    send_message_callback=None,
                    preview=preview,
                    rationale_switch=rationale_switch,
                    language=language,
                    user_email=user_email,
                    session_id=session_id
                )
            print("--------------------------------")
            print(f"[DEBUG] Event: {event}")
            print("--------------------------------")

        if preview and user_email:
            send_preview_message_to_websocket(
                project_uuid=str(project_uuid),
                user_email=user_email,
                message_data={
                    "type": "status",
                    "content": "Processing complete",
                    "session_id": session_id
                }
            )

        return full_response
