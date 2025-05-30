import logging
import os
import boto3
import unicodedata
from nexus.environment import env
from typing import List, Dict, Optional, Callable

from nexus.celery import app as celery_app
from nexus.event_domain.event_observer import EventObserver
from nexus.usecases.inline_agents.typing import TypingUsecase
from router.clients.flows.http.send_message import SendMessageHTTPClient
from router.traces_observers.save_traces import save_inline_message_to_database
from router.clients.preview.simulator.broadcast import SimulateBroadcast

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class RationaleObserver(EventObserver):
    CACHE_TIMEOUT = 300  # 5 minutes in seconds

    def __init__(self, bedrock_client=None, model_id=None):
        """
        Initialize the RationaleObserver.

        Args:
            bedrock_client: Optional Bedrock client for testing
            model_id: Optional model ID for testing
        """
        self.bedrock_client = bedrock_client or self._get_bedrock_client()
        self.model_id = model_id or settings.AWS_RATIONALE_MODEL
        self.flows_user_email = os.environ.get("FLOW_USER_EMAIL")

    def _get_bedrock_client(self):
        region_name = env.str('AWS_BEDROCK_REGION_NAME')
        return boto3.client(
            "bedrock-runtime",
            region_name=region_name
        )

    def _handle_preview_message(
        self,
        text: str,
        urns: list,
        project_uuid: str,
        user: str,
        user_email: str,
        full_chunks: list[Dict] = None
    ) -> None:
        from nexus.usecases.intelligences.retrieve import get_file_info
        from nexus.projects.websockets.consumers import send_preview_message_to_websocket

        if not full_chunks:
            full_chunks = []

        broadcast = SimulateBroadcast(
            os.environ.get('FLOWS_REST_ENDPOINT'),
            os.environ.get('FLOWS_INTERNAL_TOKEN'),
            get_file_info
        )

        preview_response = broadcast.send_direct_message(
            text=text,
            urns=urns,
            project_uuid=project_uuid,
            user=user,
            full_chunks=full_chunks
        )

        send_preview_message_to_websocket(
            project_uuid=str(project_uuid),
            user_email=user_email,
            message_data={
                "type": "preview",
                "content": preview_response
            }
        )

    def _get_session_data(self, session_id: str) -> dict:
        """Get or create session data from cache."""
        cache_key = f"rationale_session_{session_id}"
        session_data = cache.get(cache_key)

        if session_data is None:
            session_data = {
                'rationale_history': [],
                'first_rationale_text': None,
                'is_first_rationale': True
            }
            cache.set(cache_key, session_data, self.CACHE_TIMEOUT)

        return session_data

    def _save_session_data(self, session_id: str, session_data: dict) -> None:
        """Save session data to cache."""
        cache_key = f"rationale_session_{session_id}"
        cache.set(cache_key, session_data, self.CACHE_TIMEOUT)

    def perform(
        self,
        inline_traces: Dict,
        session_id: str,
        user_input: str = "",
        contact_urn: str = "",
        project_uuid: str = "",
        send_message_callback: Optional[Callable] = None,
        preview: bool = False,
        rationale_switch: bool = False,
        message_external_id: str = "",
        user_email: str = None,
        turn_off_rationale: bool = False,
        **kwargs
    ) -> None:

        if not rationale_switch or turn_off_rationale:
            return

        print("[DEBUG] Rationale Observer")
        typing_usecase = TypingUsecase()
        try:
            if not self._validate_traces(inline_traces):
                return

            # Get session data
            session_data = self._get_session_data(session_id)

            if send_message_callback is None:
                if message_external_id:
                    typing_usecase.send_typing_message(
                        contact_urn=contact_urn,
                        msg_external_id=message_external_id,
                        project_uuid=project_uuid,
                        preview=preview
                    )

                def send_message(text, urns, project_uuid, user, full_chunks=None):
                    return self.task_send_rationale_message.delay(
                        text=text,
                        urns=urns,
                        project_uuid=project_uuid,
                        user=user,
                        full_chunks=full_chunks,
                        preview=preview,
                        user_email=user_email
                    )

                send_message_callback = send_message
            if message_external_id:
                typing_usecase.send_typing_message(
                    contact_urn=contact_urn,
                    msg_external_id=message_external_id,
                    project_uuid=project_uuid,
                    preview=preview
                )

            rationale_text = self._extract_rationale_text(inline_traces)

            # Process the rationale if found
            if rationale_text:
                if not session_data['is_first_rationale']:

                    improved_text = self._improve_subsequent_rationale(
                        rationale_text=rationale_text,
                        previous_rationales=session_data['rationale_history'],
                        user_input=user_input
                    )

                    if self._is_valid_rationale(improved_text):
                        session_data['rationale_history'].append(improved_text)
                        self._save_session_data(session_id, session_data)
                        if message_external_id:
                            typing_usecase.send_typing_message(
                                contact_urn=contact_urn,
                                msg_external_id=message_external_id,
                                project_uuid=project_uuid,
                                preview=preview
                            )
                        self._send_rationale_message(
                            text=improved_text,
                            contact_urn=contact_urn,
                            project_uuid=project_uuid,
                            session_id=session_id,
                            send_message_callback=send_message_callback
                        )
                        if message_external_id:
                            typing_usecase.send_typing_message(
                                contact_urn=contact_urn,
                                msg_external_id=message_external_id,
                                project_uuid=project_uuid,
                                preview=preview
                            )

            # Handle first rationale if it exists and we have caller chain info
            if session_data['is_first_rationale'] and self._has_caller_chain(inline_traces) and rationale_text:

                if message_external_id:
                    typing_usecase.send_typing_message(
                        contact_urn=contact_urn,
                        msg_external_id=message_external_id,
                        project_uuid=project_uuid,
                        preview=preview
                    )
                improved_text = self._improve_rationale_text(
                    rationale_text=rationale_text,
                    user_input=user_input,
                    is_first_rationale=True
                )
                if message_external_id:
                    typing_usecase.send_typing_message(
                        contact_urn=contact_urn,
                        msg_external_id=message_external_id,
                        project_uuid=project_uuid,
                        preview=preview
                    )

                if self._is_valid_rationale(improved_text):
                    session_data['rationale_history'].append(improved_text)
                    self._save_session_data(session_id, session_data)
                    if message_external_id:
                        typing_usecase.send_typing_message(
                            contact_urn=contact_urn,
                            msg_external_id=message_external_id,
                            project_uuid=project_uuid,
                            preview=preview
                        )
                    self._send_rationale_message(
                        text=improved_text,
                        contact_urn=contact_urn,
                        project_uuid=project_uuid,
                        session_id=session_id,
                        send_message_callback=send_message_callback
                    )
                    session_data['is_first_rationale'] = False

                    if message_external_id:
                        typing_usecase.send_typing_message(
                            contact_urn=contact_urn,
                            msg_external_id=message_external_id,
                            project_uuid=project_uuid,
                            preview=preview
                        )
                if message_external_id:
                    typing_usecase.send_typing_message(
                        contact_urn=contact_urn,
                        msg_external_id=message_external_id,
                        project_uuid=project_uuid,
                        preview=preview
                    )
                session_data['first_rationale_text'] = None
                self._save_session_data(session_id, session_data)

        except Exception as e:
            logger.error(f"Error processing rationale: {str(e)}", exc_info=True)

    def _validate_traces(self, inline_traces: Dict) -> bool:
        return inline_traces is not None and 'trace' in inline_traces

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

    def _has_caller_chain(self, inline_traces: Dict) -> bool:
        try:
            if 'callerChain' in inline_traces:
                caller_chain = inline_traces['callerChain']
                return isinstance(caller_chain, list) and len(caller_chain) >= 1
            return False
        except Exception as e:
            logger.error(f"Error checking caller chain: {str(e)}", exc_info=True)
            return False

    def _is_valid_rationale(self, rationale_text: str) -> bool:
        text = rationale_text.lower()
        text = self._remove_accents(text)
        valid_rationale = not text.startswith("invalid")
        return valid_rationale

    def _send_rationale_message(
        self,
        text: str,
        contact_urn: str,
        project_uuid: str,
        session_id: str,
        send_message_callback: Callable,
    ) -> None:
        try:
            send_message_callback(
                text=text,
                urns=[contact_urn],
                project_uuid=project_uuid,
                user=self.flows_user_email,
            )
            save_inline_message_to_database(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                text=text,
                preview=False,
                session_id=session_id,
                source_type="agent"
            )
        except Exception as e:
            logger.error(f"Error sending rationale message: {str(e)}", exc_info=True)

    def _remove_accents(self, text: str) -> str:

        return ''.join(
            c for c in unicodedata.normalize(
                'NFD', text
            )
            if unicodedata.category(c) != 'Mn'
        )

    def _improve_rationale_text(
        self,
        rationale_text: str,
        user_input: str = "",
        is_first_rationale: bool = False
    ) -> str:
        try:
            # Prepare the complete instruction content for the user message
            instruction_content = settings.RATIONALE_IMPROVEMENT_INSTRUCTIONS

            if user_input:
                instruction_content += f"""
                    <user_message>{user_input}</user_message>
                """

            # Add the rationale text to analyze
            instruction_content += f"""
                <thought>{rationale_text}</thought>
            """

            # Build conversation with just one user message and an expected assistant response
            conversation = [
                # Single user message with all instructions and the rationale to analyze
                {
                    "role": "user",
                    "content": [{"text": instruction_content}]
                }
            ]

            print("------------------------------------------------")
            print(f"[DEBUG] Instruction content FIRST RATIONALE: {instruction_content}")
            print("------------------------------------------------")

            # Send the request to Amazon Bedrock
            response = self.bedrock_client.converse(
                modelId=self.model_id,
                messages=conversation,
                inferenceConfig={
                    "maxTokens": 150,
                    "temperature": 0,
                }
            )

            logger.debug(f"Improvement Response: {response}")
            # Extract the response text
            response_text = response["output"]["message"]["content"][0]["text"]

            # For first rationales, make sure they're never "invalid"
            if is_first_rationale and response_text.strip().lower() == "invalid":
                # If somehow still got "invalid", force a generic improvement
                return "Processando sua solicitação agora."

            # Remove any quotes from the response
            return response_text.strip().strip('"\'')
        except Exception as e:
            logger.error(f"Error improving rationale text: {str(e)}", exc_info=True)
            return rationale_text  # Return original text if transformation fails

    def _improve_subsequent_rationale(
        self,
        rationale_text: str,
        previous_rationales: List[str] = [],
        user_input: str = ""
    ) -> str:
        try:
            # Prepare the complete instruction content for the user message
            instruction_content = settings.SUBSEQUENT_RATIONALE_INSTRUCTIONS

            # Add user input context if available
            if user_input:
                instruction_content += f"<user_message>{user_input}</user_message>"

            if previous_rationales:
                instruction_content += f"""
                <previous_thought>
                {' '.join([f"- {r}" for r in previous_rationales])}
                </previous_thought>
                """

            # Add the rationale text to analyze
            instruction_content += f"<main_thought>{rationale_text}</main_thought>"

            # Build conversation with just one user message and an expected assistant response
            conversation = [
                # Single user message with all instructions and the rationale to analyze
                {
                    "role": "user",
                    "content": [{"text": instruction_content}]
                }
            ]

            print("------------------------------------------------")
            print(f"[DEBUG] Instruction content SUBSEQUENT RATIONALE: {instruction_content}")
            print("------------------------------------------------")

            # Send the request to Amazon Bedrock
            response = self.bedrock_client.converse(
                modelId=self.model_id,
                messages=conversation,
                inferenceConfig={
                    "maxTokens": 150,
                    "temperature": 0
                }
            )

            # Extract the response text
            response_text = response["output"]["message"]["content"][0]["text"]

            # Remove any quotes from the response
            return response_text.strip().strip('"\'')
        except Exception as e:
            logger.error(f"Error improving subsequent rationale text: {str(e)}", exc_info=True)
            return rationale_text  # Return original text if transformation fails

    @staticmethod
    @celery_app.task
    def task_send_rationale_message(
        text: str,
        urns: list,
        project_uuid: str,
        user: str,
        full_chunks: list[Dict] = None,
        preview: bool = False,
        user_email: str = None
    ) -> None:

        if preview and user_email:
            observer = RationaleObserver()
            observer._handle_preview_message(
                text=text,
                urns=urns,
                project_uuid=project_uuid,
                user=user,
                user_email=user_email,
                full_chunks=full_chunks
            )

        # Always send the actual message
        broadcast = SendMessageHTTPClient(
            os.environ.get(
                'FLOWS_REST_ENDPOINT'
            ),
            os.environ.get(
                'FLOWS_SEND_MESSAGE_INTERNAL_TOKEN'
            )
        )

        broadcast.send_direct_message(
            text=text,
            urns=urns,
            project_uuid=project_uuid,
            user=user,
            full_chunks=full_chunks
        )
