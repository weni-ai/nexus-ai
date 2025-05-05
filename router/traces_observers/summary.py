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

            prompt = f"""You are an expert summarizer.

            Goal
            -----
            Create **one sentence (≤10 words)** that captures the orchestrator's current action, always referring to any action as a **tool**.

            Language
            ---------
            Write the sentence in **{language}**.
            - If {language}.lower().startswith("pt"): use natural Brazilian Portuguese.
            - Otherwise, write in English.

            Phrase templates
            -----------------
            Choose the first matching item in the JSON trace and use its phrase.
            For PT / EN translations, follow the mapping shown:

            - guardrailTrace → {{ "pt": "Aplicando guardrails", "en": "Applying guardrails" }}
            - modelInvocationInput → {{ "pt": "Invocando modelo", "en": "Invoking model" }}
            - modelInvocationOutput → {{ "pt": "Resposta do modelo recebida", "en": "Received model response" }}
            - rationale → {{ "pt": "Pensando sobre {{topic}}", "en": "Thinking about {{topic}}" }}
            - agentCollaboratorInvocationInput → {{ "pt": "Delegando ao agente {{agent}}", "en": "Delegating to agent {{agent}}" }}
            - actionGroupInvocationInput → {{ "pt": "Chamando tool {{func}}", "en": "Calling tool {{func}}" }}
            - actionGroupInvocationOutput → {{ "pt": "Saída da tool {{func}} recebida", "en": "Received output of tool {{func}}" }}
            - agentCollaboratorInvocationOutput / finalResponse
                → {{ "pt": "Resultado do agente {{agent}} recebido", "en": "Agent {{agent}} result received" }}

            Rules
            ------
            1. Start with a suitable gerund/verb (e.g., Verificando / Checking).
            2. Replace {{topic}}, {{agent}}, {{func}} with meaningful terms from the trace when they exist.
            3. If none of the templates match, craft a generic gerund summary (≤ 10 words).
            4. Do **not** expose technical details (model names, architectures, language codes, etc.).

            JSON trace to summarize
            ------------------------
            {json.dumps(trace_data, indent=2)}
            """

            response = client.chat.completions.create(
                model="gpt-4.1-nano",
                temperature=0,
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
