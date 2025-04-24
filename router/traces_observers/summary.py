import json
import time
import logging

from openai import OpenAI
from django.conf import settings
from nexus.event_domain.event_observer import EventObserver


class SummaryTracesObserver(EventObserver):
    """
    This observer is responsible for:
    - Generating a summary of the traces of the action.
    - Saving the summary on the database.
    - Sending trace updates to the websocket when in preview mode.

    It's designed to work with both the start_multi_agents function and the BedrockBackend's invoke_agents method.
    """
    def perform(
        self,
        language="en",
        event_content=None,
        inline_traces=None,
        preview=False,
        project_uuid=None,
        user_email=None,
        session_id=None,
        **kwargs
    ):
        # TODO: Fix circular import
        from nexus.projects.websockets.consumers import send_preview_message_to_websocket

        if not preview:
            return

        print("[DEBUG] Summary Traces Observer")

        try:
            # Determine which trace data to use
            trace_data = inline_traces if inline_traces is not None else event_content

            if not trace_data:
                logging.warning("No trace data provided to SummaryTracesObserver")
                return

            client = OpenAI()
            # Add a small delay between API calls to respect rate limits
            if settings.TRACE_SUMMARY_DELAY:
                time.sleep(3)

            prompt = f"""
            Generate a concise, one-line summary of the trace of the action, in {language}.
            This summary must describe the orchestrator's action, referring to all actions as "skills."

            Guidelines for your response:
            - Use the following language for the summary: {language}.
            - The text to be summarized is the trace of the action.
            - Use a systematic style (e.g., "Cancel Order skill activated", "Forwarding request to Reporting skill").
            - The summary must not exceed 10 words.
            - Use varied gerunds (e.g., "Checking", "Cancelling", "Forwarding").
            - Do not include technical details about models, architectures, language codes, or anything unrelated to summarizing the action.

            Here is the trace of the action:
            {json.dumps(trace_data, indent=2)}
            """

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=100,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            summary = response.choices[0].message.content

            trace_data['summary'] = summary

            if user_email and project_uuid and session_id:
                send_preview_message_to_websocket(
                    project_uuid=str(project_uuid),
                    user_email=user_email,
                    message_data={
                        "type": "trace_update",
                        "trace": trace_data,
                        "session_id": session_id
                    }
                )

            return summary
        except Exception as e:
            logging.error(f"Error getting trace summary: {str(e)}")
            return "Processing your request now"
