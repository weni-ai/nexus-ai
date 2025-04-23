import logging
import os
import boto3
from nexus.environment import env
from typing import List, Dict, Optional, Callable

from nexus.celery import app as celery_app
from nexus.event_domain.event_observer import EventObserver
from router.clients.flows.http.send_message import SendMessageHTTPClient
from router.traces_observers.save_traces import save_inline_message_to_database

from django.conf import settings

logger = logging.getLogger(__name__)

# Constants for instruction content
RATIONALE_IMPROVEMENT_INSTRUCTIONS = """
    You are an agent specialized in sending notifications to your user. They are waiting for a response to a request, but before receiving it, you need to notify them with precision about what you're doing, in a way that truly helps them. To do this, you will receive a thought and should rephrase it by following principles to make it fully useful to the user.

    The thought you will receive to rephrase will be between the <thought><thought> tags.

    You can also use the user's message to base the rephrasing of the thought. The user's message will be between the <user_message></user_message> tags.

    For the rephrasing, you must follow principles. These will be between the <principles></principles> tags, and you should give them high priority.

    <principles>
    - Keeping it concise and direct (max 15 words);
    - The rephrasing should always be in the first person (you are the one thinking);
    - Your output is always in the present tense;
    - Removing conversation starters and technical jargon;
    - Clearly stating the current action or error condition;
    - Preserving essential details from the original rationale;
    - Returning ONLY the transformed text with NO additional explanation or formatting;- Your output should ALWAYS be in the language of the user's message.
    </principles>

    You can find examples of rephrasings within the tags <examples></examples>.

    <examples>
    # EXAMPLE 1 
    Tought: Consulting ProductConcierge for formal clothing suggestions.
    Rephrasing: I'm looking for formal clothes for you!
    # EXAMPLE 2
    Tought: The user is looking for flights from Miami to New York for one person, with specific dates. I will use the travel agent to search for this information.
    Rephrasing: Checking flights from Miami to New York on specified dates.
    # EXAMPLE 3
    Tought: I received an error because the provided dates are in the past. I need to inform the user that future dates are required for the search.
    Rephrasing: Dates provided are in the past, future dates needed.</examples>
"""

SUBSEQUENT_RATIONALE_INSTRUCTIONS = """
    You are a message analyst responsible for reviewing messages from an artificial agent that may or may not be sent to the end user.

    You will receive the agent's main thought, and your first task is to determine whether this thought is invalid for sending to the end user. The main thought will be enclosed within the tags <main_thought></main_thought>.

    To decide if a thought is valid, you must analyze a list of criteria that classify a thought as invalid, as well as review previous thoughts. These previous thoughts will be enclosed within the tags <previous_thought></previous_thought>. The list of criteria you must analyze to determine if a thought is invalid will be enclosed within the tags <invalid_thought></invalid_thought>. Another important piece of information for your analysis is the user's message, which will be enclosed within the tags <user_message></user_message>.

    <invalid_thought>
        - Contains greetings, generic assistance, or simple acknowledgments
        - Mentions internal components (e.g., "ProductConcierge") without adding value
        - Describes communication actions with the user (e.g., "I will inform the user")
        - Is vague, generic, or lacks specific actionable content
        - Conveys essentially the same information as any previous rationale, even if worded differently
        - Addresses the same topic or message as the immediately previous rationale
    </invalid_thought>

    If the thought is considered invalid, write only 'invalid'. Write NOTHING else besides 'invalid'.

    If the thought is valid, you must REWRITE IT following the rewriting principles. These principles will be within the tags <principles></principles> and must be HIGHLY prioritized if the thought is considered valid.

    <principles>
        - Keeping it concise and direct (max 15 words);
        - The rephrasing should always be in the first person (you are the one thinking);
        - Your output is always in the present tense;
        - Removing conversation starters and technical jargon;
        - Clearly stating the current action or error condition;
        - Preserving essential details from the original rationale;
        - Returning ONLY the transformed text with NO additional explanation or formatting;
        - Your output should ALWAYS be in the language of the user's message.
    </principles>

    You can find examples of rephrasings within the tags <examples></examples>.

    <examples>
    # EXAMPLE 1
    Tought: Consulting ProductConcierge for formal clothing suggestions.
    Rephrasing: I'm looking for formal clothes for you!
    # EXAMPLE 2
    Tought: The user is looking for flights from Miami to New York for one person, with specific dates. I will use the travel agent to search for this information.
    Rephrasing: Checking flights from Miami to New York on specified dates.
    # EXAMPLE 3
    Tought: I received an error because the provided dates are in the past. I need to inform the user that future dates are required for the search.
    Rephrasing: Dates provided are in the past, future dates needed.
    </examples>
"""


class RationaleObserver(EventObserver):

    def __init__(self, bedrock_client=None, model_id=None):
        """
        Initialize the RationaleObserver.

        Args:
            bedrock_client: Optional Bedrock client for testing
            model_id: Optional model ID for testing
        """
        self.bedrock_client = bedrock_client or self._get_bedrock_client()
        self.model_id = model_id or settings.AWS_RATIONALE_MODEL
        self.rationale_history = []
        self.first_rationale_text = None
        self.is_first_rationale = True
        self.flows_user_email = os.environ.get("FLOW_USER_EMAIL")

    def _get_bedrock_client(self):
        region_name = env.str('AWS_BEDROCK_REGION_NAME')
        return boto3.client(
            "bedrock-runtime",
            region_name=region_name
        )

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
        **kwargs
    ) -> None:
        print(f"[DEBUG] Rationale Observer")

        if preview or not rationale_switch:
            return

        try:
            if not self._validate_traces(inline_traces):
                return

            if send_message_callback is None:
                send_message_callback = self.task_send_rationale_message.delay

            rationale_text = self._extract_rationale_text(inline_traces)

            # Process the rationale if found
            if rationale_text:
                if self.is_first_rationale:
                    self.first_rationale_text = rationale_text
                    self.is_first_rationale = False
                else:
                    improved_text = self._improve_subsequent_rationale(
                        rationale_text,
                        self.rationale_history,
                        user_input
                    )

                    if self._is_valid_rationale(improved_text):
                        self.rationale_history.append(improved_text)
                        self._send_rationale_message(
                            text=improved_text,
                            contact_urn=contact_urn,
                            project_uuid=project_uuid,
                            session_id=session_id,
                            send_message_callback=send_message_callback
                        )

            # Handle first rationale if it exists and we have caller chain info
            if self.first_rationale_text and self._has_caller_chain(inline_traces):
                improved_text = self._improve_rationale_text(
                    self.first_rationale_text,
                    self.rationale_history,
                    user_input,
                    is_first_rationale=True
                )

                if self._is_valid_rationale(improved_text):
                    self.rationale_history.append(improved_text)
                    self._send_rationale_message(
                        text=improved_text,
                        contact_urn=contact_urn,
                        project_uuid=project_uuid,
                        session_id=session_id,
                        send_message_callback=send_message_callback
                    )
                self.first_rationale_text = None

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
                return isinstance(caller_chain, list) and len(caller_chain) > 1
            return False
        except Exception as e:
            logger.error(f"Error checking caller chain: {str(e)}", exc_info=True)
            return False

    def _is_valid_rationale(self, rationale_text: str) -> bool:
        return rationale_text.lower() != "invalid"

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
            )
        except Exception as e:
            logger.error(f"Error sending rationale message: {str(e)}", exc_info=True)

    def _improve_rationale_text(
        self,
        rationale_text: str,
        user_input: str = "",
        is_first_rationale: bool = False
    ) -> str:
        try:
            # Prepare the complete instruction content for the user message
            instruction_content = RATIONALE_IMPROVEMENT_INSTRUCTIONS

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
            instruction_content = SUBSEQUENT_RATIONALE_INSTRUCTIONS

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
        full_chunks: list[Dict] = None
    ) -> None:
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
