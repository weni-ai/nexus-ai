import logging
from typing import Dict, Optional, List

import boto3
from django.template.defaultfilters import slugify

from inline_agents.backend import InlineAgentsBackend
from nexus.environment import env
from nexus.inline_agents.backends.bedrock.repository import (
    BedrockSupervisorRepository,
)
from nexus.projects.websockets.consumers import (
    send_preview_message_to_websocket,
)
from nexus.usecases.inline_agents.typing import TypingUsecase
from nexus.usecases.jwt.jwt_usecase import JWTUsecase
from router.traces_observers.save_traces import save_inline_message_to_database

from .adapter import BedrockTeamAdapter, BedrockDataLakeEventAdapter
from router.handler import PostMessageHandler
from inline_agents.adapter import DataLakeEventAdapter
from nexus.projects.models import Project


logger = logging.getLogger(__name__)


def _get_lambda_usecase():
    from nexus.usecases.intelligences.lambda_usecase import LambdaUseCase
    return LambdaUseCase()


class BedrockBackend(InlineAgentsBackend):
    supervisor_repository = BedrockSupervisorRepository
    team_adapter = BedrockTeamAdapter

    REGION_NAME = env.str('AWS_BEDROCK_REGION_NAME')

    def __init__(self):
        super().__init__()
        self._event_manager_notify = None
        self._data_lake_event_adapter = None

    def _get_client(self):
        return boto3.client('bedrock-agent-runtime', region_name=self.REGION_NAME)

    def _get_event_manager_notify(self):
        if self._event_manager_notify is None:
            from nexus.events import event_manager
            self._event_manager_notify = event_manager.notify
        return self._event_manager_notify

    def _get_data_lake_event_adapter(self):
        if self._data_lake_event_adapter is None:
            self._data_lake_event_adapter = BedrockDataLakeEventAdapter()
        return self._data_lake_event_adapter

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
        contact_name: str = "",
        channel_uuid: str = "",
        msg_external_id: str = None,
        turn_off_rationale: bool = False,
        event_manager_notify: callable = None,
        data_lake_event_adapter: DataLakeEventAdapter = None,
        use_prompt_creation_configurations: bool = False,
        conversation_turns_to_include: int = 10,
        exclude_previous_thinking_steps: bool = True,
        foundation_model: str = None,
        project: Project = None,
        stream: bool = False,
        **kwargs,
    ):
        # Input validation
        if not input_text or not input_text.strip():
            raise ValueError("input_text cannot be empty")
        if not project_uuid:
            raise ValueError("project_uuid is required")
        if not contact_urn:
            raise ValueError("contact_urn is required")
        if conversation_turns_to_include < 0:
            raise ValueError("conversation_turns_to_include must be non-negative")
        if stream:
            return self._invoke_agents_streaming(
                team=team,
                input_text=input_text,
                contact_urn=contact_urn,
                project_uuid=project_uuid,
                sanitized_urn=sanitized_urn,
                preview=preview,
                rationale_switch=rationale_switch,
                language=language,
                user_email=user_email,
                use_components=use_components,
                contact_fields=contact_fields,
                contact_name=contact_name,
                channel_uuid=channel_uuid,
                msg_external_id=msg_external_id,
                turn_off_rationale=turn_off_rationale,
                event_manager_notify=event_manager_notify,
                data_lake_event_adapter=data_lake_event_adapter,
                use_prompt_creation_configurations=use_prompt_creation_configurations,
                conversation_turns_to_include=conversation_turns_to_include,
                exclude_previous_thinking_steps=exclude_previous_thinking_steps,
                foundation_model=foundation_model,
                project=project,
                **kwargs,
            )
        else:
            return self._invoke_agents_blocking(
                team=team,
                input_text=input_text,
                contact_urn=contact_urn,
                project_uuid=project_uuid,
                sanitized_urn=sanitized_urn,
                preview=preview,
                rationale_switch=rationale_switch,
                language=language,
                user_email=user_email,
                use_components=use_components,
                contact_fields=contact_fields,
                contact_name=contact_name,
                channel_uuid=channel_uuid,
                msg_external_id=msg_external_id,
                turn_off_rationale=turn_off_rationale,
                event_manager_notify=event_manager_notify,
                data_lake_event_adapter=data_lake_event_adapter,
                use_prompt_creation_configurations=use_prompt_creation_configurations,
                conversation_turns_to_include=conversation_turns_to_include,
                exclude_previous_thinking_steps=exclude_previous_thinking_steps,
                foundation_model=foundation_model,
                project=project,
                **kwargs,
            )

    def _invoke_agents_blocking(
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
        contact_name: str = "",
        channel_uuid: str = "",
        msg_external_id: str = None,
        turn_off_rationale: bool = False,
        event_manager_notify: callable = None,
        data_lake_event_adapter: DataLakeEventAdapter = None,
        use_prompt_creation_configurations: bool = False,
        conversation_turns_to_include: int = 10,
        exclude_previous_thinking_steps: bool = True,
        foundation_model: str = None,
        project: Project = None,
        **kwargs,
    ):
        """Maintains compatibility - returns complete string"""
        full_response = ""
        trace_events = []
        rationale_traces = []
        session_id = None
        
        for chunk_data in self._invoke_agents_streaming(
            team=team,
            input_text=input_text,
            contact_urn=contact_urn,
            project_uuid=project_uuid,
            sanitized_urn=sanitized_urn,
            preview=preview,
            rationale_switch=rationale_switch,
            language=language,
            user_email=user_email,
            use_components=use_components,
            contact_fields=contact_fields,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
            msg_external_id=msg_external_id,
            turn_off_rationale=turn_off_rationale,
            event_manager_notify=event_manager_notify,
            data_lake_event_adapter=data_lake_event_adapter,
            use_prompt_creation_configurations=use_prompt_creation_configurations,
            conversation_turns_to_include=conversation_turns_to_include,
            exclude_previous_thinking_steps=exclude_previous_thinking_steps,
            foundation_model=foundation_model,
            project=project,
            **kwargs,
        ):
            if chunk_data['type'] == 'chunk':
                full_response += chunk_data['content']
            elif chunk_data['type'] == 'complete':
                trace_events = chunk_data['trace_events']
                rationale_traces = chunk_data['rationale_traces']
                session_id = chunk_data['session_id']
        
        # Final processing
        self._event_manager_notify(
            event='save_inline_trace_events',
            trace_events=trace_events,
            project_uuid=project_uuid,
            user_input=input_text,
            contact_urn=contact_urn,
            agent_response=full_response,
            preview=preview,
            session_id=session_id,
            source_type="agent",
            contact_name=contact_name,
            channel_uuid=channel_uuid
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

        rationale_texts = self._extract_rationale_text(rationale_traces)
        full_response = self._handle_rationale_in_response(
            rationale_texts=rationale_texts,
            full_response=full_response,
        )

            post_message_handler = PostMessageHandler()
            full_response = post_message_handler.handle_post_message(full_response)

            return full_response
            
        except Exception as e:
            logger.error(f"Error in blocking mode for project {project_uuid}: {str(e)}", exc_info=True)
            raise

    def _invoke_agents_streaming(
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
        contact_name: str = "",
        channel_uuid: str = "",
        msg_external_id: str = None,
        turn_off_rationale: bool = False,
        event_manager_notify: callable = None,
        data_lake_event_adapter: DataLakeEventAdapter = None,
        use_prompt_creation_configurations: bool = False,
        conversation_turns_to_include: int = 10,
        exclude_previous_thinking_steps: bool = True,
        foundation_model: str = None,
        project: Project = None,
        **kwargs,
    ):
        """Streaming version that yields chunks in real-time"""
        try:
            supervisor = self.supervisor_repository.get_supervisor(project=project, foundation_model=foundation_model)
            if not supervisor:
                raise ValueError(f"Supervisor not found for project {project_uuid}")

            # Set dependencies
            self._event_manager_notify = event_manager_notify or self._get_event_manager_notify()
            self._data_lake_event_adapter = data_lake_event_adapter or self._get_data_lake_event_adapter()

            typing_usecase = TypingUsecase()
            typing_usecase.send_typing_message(
                contact_urn=contact_urn,
                msg_external_id=msg_external_id,
                project_uuid=project_uuid,
                preview=preview
            )

            jwt_usecase = JWTUsecase()
            auth_token = jwt_usecase.generate_jwt_token(project_uuid)

            external_team = self.team_adapter.to_external(
                supervisor=supervisor,
                agents=team,
                input_text=input_text,
                contact_urn=contact_urn,
                project_uuid=project_uuid,
                use_components=use_components,
                contact_fields=contact_fields,
                contact_name=contact_name,
                channel_uuid=channel_uuid,
                auth_token=auth_token,
                sanitized_urn=sanitized_urn,
                project=project,
                content_base=kwargs.get('content_base')
            )

            if use_prompt_creation_configurations:
                external_team["promptCreationConfigurations"] = {
                    "excludePreviousThinkingSteps": exclude_previous_thinking_steps,
                    "previousConversationTurnsToInclude": conversation_turns_to_include,
                }

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
                source_type="user",
                contact_name=contact_name,
                channel_uuid=channel_uuid
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
            
            if not response or "completion" not in response:
                raise ValueError("Invalid response from Bedrock client")

            completion = response["completion"]
            trace_events = []
            rationale_traces = []

            for event in completion:
                try:
                    if 'chunk' in event:
                        chunk_bytes = event.get('chunk', {}).get('bytes')
                        if not chunk_bytes:
                            logger.warning(f"Empty chunk received for session {session_id}")
                            continue
                            
                        chunk = chunk_bytes.decode('utf-8')
                        
                        # Yield chunk data
                        yield {
                            'type': 'chunk',
                            'content': chunk,
                            'session_id': session_id
                        }
                        
                        self._process_chunk_events(chunk, event, preview, user_email, project_uuid, session_id)

                    if 'trace' in event:
                        trace_data = event.get('trace')
                        if not trace_data:
                            logger.warning(f"Empty trace received for session {session_id}")
                            continue
                            
                        trace_events.append(trace_data)
                        
                        # Yield trace data
                        yield {
                            'type': 'trace',
                            'data': trace_data,
                            'session_id': session_id
                        }
                        
                        self._process_trace_events(
                            trace_data, event, rationale_traces, supervisor, project_uuid, 
                            contact_urn, channel_uuid, preview, input_text, rationale_switch,
                            language, user_email, session_id, msg_external_id, turn_off_rationale,
                            typing_usecase
                        )
                except Exception as e:
                    logger.error(f"Error processing event in streaming: {str(e)}", exc_info=True)
                    yield {
                        'type': 'error',
                        'error': str(e),
                        'session_id': session_id
                    }

            # Final processing and cleanup
            yield {
                'type': 'complete',
                'trace_events': trace_events,
                'rationale_traces': rationale_traces,
                'session_id': session_id
            }
            
        except Exception as e:
            logger.error(f"Critical error in streaming for session {session_id}: {str(e)}", exc_info=True)
            yield {
                'type': 'error',
                'error': f"Streaming failed: {str(e)}",
                'session_id': session_id or 'unknown'
            }

    def _process_chunk_events(self, chunk, event, preview, user_email, project_uuid, session_id):
        """Process chunk events for WebSocket and logging"""
        try:
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
            print("------------------------------------------")
            print("Chunk: ", event)
            print("------------------------------------------")
        except Exception as e:
            logger.error(f"Error processing chunk events: {str(e)}", exc_info=True)

    def _process_trace_events(self, trace_data, event, rationale_traces, supervisor, 
                            project_uuid, contact_urn, channel_uuid, preview, input_text,
                            rationale_switch, language, user_email, session_id, 
                            msg_external_id, turn_off_rationale, typing_usecase):
        """Process trace events for data lake and observers"""
        collaborator_name = event.get("collaboratorName", "")
        orchestration_trace = trace_data.get("trace", {}).get("orchestrationTrace", {})
        collaborator_foundation_model = orchestration_trace.get("modelInvocationInput", {}).get("foundationModel", "")

        self._data_lake_event_adapter.custom_event_data(
            inline_trace=trace_data,
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            preview=preview,
            collaborator_name=collaborator_name
        )

        self._data_lake_event_adapter.to_data_lake_event(
            inline_trace=trace_data,
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            preview=preview,
            backend="bedrock",
            foundation_model=collaborator_foundation_model if collaborator_foundation_model else supervisor.get("foundation_model", "")
        )

        if "rationale" in orchestration_trace:
            rationale_traces.append(trace_data)

        if "rationale" in orchestration_trace and msg_external_id and not preview:
            typing_usecase.send_typing_message(
                contact_urn=contact_urn,
                project_uuid=project_uuid,
                msg_external_id=msg_external_id,
                preview=preview
            )

        self._event_manager_notify(
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
            turn_off_rationale=turn_off_rationale,
            channel_uuid=channel_uuid
        )

        print("------------------------------------------")
        print("Event: ", event)
        print("------------------------------------------")

    def _handle_rationale_in_response(self, rationale_texts: Optional[List[str]], full_response: str) -> str:
        if not full_response:
            return ""

        if rationale_texts:
            for rationale_text in rationale_texts:
                if rationale_text in full_response:
                    full_response = full_response.replace(rationale_text, "").strip()

        return full_response

    def _extract_rationale_text(self, rationale_traces: List[Dict]) -> Optional[List[str]]:
        rationale_texts = []
        try:
            for trace_data in rationale_traces:
                if 'trace' in trace_data:
                    inner_trace = trace_data['trace']
                    if 'orchestrationTrace' in inner_trace:
                        orchestration = inner_trace['orchestrationTrace']
                        if 'rationale' in orchestration:
                            rationale_texts.append(orchestration['rationale'].get('text'))
            return rationale_texts
        except Exception as e:
            logger.error(f"Error extracting rationale text: {str(e)}", exc_info=True)
            return []

    def end_session(self, project_uuid: str, sanitized_urn: str):
        supervisor = self.supervisor_repository.get_supervisor(project_uuid=project_uuid)
        session_id = f"project-{project_uuid}-session-{sanitized_urn}"
        session_id = slugify(session_id)
        client = self._get_client()
        response = client.invoke_inline_agent(
            inputText="end session",
            instruction=supervisor["instruction"],
            foundationModel=supervisor["foundation_model"],
            endSession=True,
            sessionId=session_id
        )

        full_response = ""
        for event in response["completion"]:
            if 'chunk' in event:
                chunk = event['chunk']['bytes'].decode()
                full_response += chunk

        return full_response
