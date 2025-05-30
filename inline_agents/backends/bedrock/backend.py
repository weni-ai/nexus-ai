import logging
from typing import Dict, Optional

import boto3
import pendulum
import sentry_sdk
from django.template.defaultfilters import slugify

from inline_agents.backend import InlineAgentsBackend
from nexus.environment import env
from nexus.events import event_manager
from nexus.inline_agents.backends.bedrock.repository import (
    BedrockSupervisorRepository,
)
from nexus.projects.websockets.consumers import (
    send_preview_message_to_websocket,
)
from nexus.usecases.inline_agents.typing import TypingUsecase
from router.traces_observers.save_traces import save_inline_message_to_database

from .adapter import BedrockTeamAdapter

logger = logging.getLogger(__name__)


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
        user_email: str = None,
        use_components: bool = False,
        contact_fields: str = "",
        msg_external_id: str = None,
        has_attachments: bool = False
    ):
        supervisor = self.supervisor_repository.get_supervisor(project_uuid=project_uuid)

        typing_usecase = TypingUsecase()
        if not preview:
            typing_usecase.send_typing_message(
                contact_urn=contact_urn,
                msg_external_id=msg_external_id,
                project_uuid=project_uuid
            )

        external_team = self.team_adapter.to_external(
            supervisor=supervisor,
            agents=team,
            input_text=input_text,
            contact_urn=contact_urn,
            project_uuid=project_uuid,
            use_components=use_components,
            contact_fields=contact_fields,
        )
        client = self._get_client()

        # Generate a session ID for websocket communication
        session_id = f"project-{project_uuid}-session-{sanitized_urn}"
        session_id = slugify(session_id)
        log = save_inline_message_to_database(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            text=input_text,
            preview=preview,
            session_id=session_id,
            source_type="user"
        )
        print(f"[DEBUG] Session ID: {session_id}")
        print(f"[DEBUG] Log: {log}")
        print(f"[DEBUG] External team: {external_team}")

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

                orchestration_trace = trace_data.get("trace", {}).get("orchestrationTrace", {})

                if "rationale" in orchestration_trace and msg_external_id and not preview:
                    typing_usecase.send_typing_message(contact_urn=contact_urn, project_uuid=project_uuid, msg_external_id=msg_external_id)

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
                    session_id=session_id,
                    msg_external_id=msg_external_id,
                    has_attachments=has_attachments
                )

                if "rationale" in orchestration_trace and msg_external_id and not preview:
                    print("[ + Typing Indicator ] sending typing indicator")
                    typing_usecase.send_typing_message(contact_urn=contact_urn, project_uuid=project_uuid, msg_external_id=msg_external_id)
                    print("--------------------------------")

                print("------------------------------------------")
                print("Event: ", event)
                print("------------------------------------------")

        # Saving traces on s3
        self.event_manager_notify(
            event='save_inline_trace_events',
            trace_events=trace_events,
            project_uuid=project_uuid,
            user_input=input_text,
            contact_urn=contact_urn,
            agent_response=full_response,
            preview=preview,
            session_id=session_id,
            source_type="agent"  # If user message, source_type="user"
        )

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

        rationale_text = self._extract_rationale_text(trace_events)
        full_response = self._handle_rationale_in_response(
            rationale_text=rationale_text,
            full_response=full_response,
            session_id=session_id,
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            rationale_switch=rationale_switch
        )

        if "rationale" in orchestration_trace and msg_external_id and not preview:
            print("[ + Typing Indicator ] sending typing indicator")
            typing_usecase.send_typing_message(contact_urn=contact_urn, project_uuid=project_uuid, msg_external_id=msg_external_id)
            print("--------------------------------")

        return full_response

    def _handle_rationale_in_response(self, rationale_text: Optional[str], full_response: str, session_id: str, project_uuid: str, contact_urn: str, rationale_switch: bool) -> str:
        if not full_response:
            return ""

        if rationale_text and rationale_text in full_response:
            full_response = full_response.replace(rationale_text, "").strip()

            try:
                sentry_sdk.set_extra("rationale_text", rationale_text)
                sentry_sdk.set_extra("session_id", session_id)
                sentry_sdk.set_extra("project_uuid", project_uuid)
                sentry_sdk.set_extra("contact_urn", contact_urn)
                sentry_sdk.set_extra("rationale_switch", rationale_switch)
                sentry_sdk.set_extra("datetime", pendulum.now().isoformat())

                sentry_sdk.capture_message(
                    f"Rationale text found in response: {rationale_text}",
                    level="info"
                )

            except Exception as e:
                logger.error(f"Error sending rationale text to Sentry: {str(e)}: Full response: {full_response}", exc_info=True)

        return full_response

    def _extract_rationale_text(self, inline_traces: Dict) -> Optional[str]:
        try:
            trace_data = inline_traces
            if 'trace' in trace_data:
                inner_trace = trace_data['trace']
                if 'orchestrationTrace' in inner_trace:
                    orchestration = inner_trace['orchestrationTrace']
                    if 'rationale' in orchestration:
                        return orchestration['rationale'].get('text')
            return None
        except Exception as e:
            logger.error(f"Error extracting rationale text: {str(e)}", exc_info=True)
            return None
