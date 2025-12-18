import json
import logging
import time

from django.conf import settings
from openai import OpenAI

from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver


def _get_summary_prompt(language: str, trace_data: dict):
    max_trace_len = 1000
    trace_data_str = json.dumps(trace_data, indent=2)
    if len(trace_data_str) > max_trace_len:
        # Simple truncation: take the first N chars and add ellipsis
        trace_data_str = trace_data_str[:max_trace_len] + "...\n(Trace data truncated due to length)"

    prompt = f"""You are an expert summarizer.

Goal
-----
Create **one sentence (≤10 words)** that captures the orchestrator's current action.

Language
---------
Write the sentence in **{language}**.
- If {language}.lower().startswith("pt"): use natural Brazilian Portuguese.
- Otherwise, write in English.

**How to Generate the Summary (Follow these steps IN ORDER):**

**Step 1: Check for a Matching Action Key and Use its EXACT Template**

*   **Priority 1: Check inside `trace.orchestrationTrace` (if it exists):**
    *   Look for the **first key** in `trace.orchestrationTrace` that matches one of these
        (**excluding** `rationale` for now):
        *   Condition: Key is `invocationInput` AND its `invocationType` property is `"KNOWLEDGE_BASE"`
            → **Use exactly:** `{{ "pt": "Consultando base de conhecimento", "en": "Searching Knowledge Base" }}`
        *   Key: `modelInvocationInput` → **Use exactly:** `{{ "pt": "Invocando modelo", "en": "Invoking model" }}`
            (This key takes precedence. Use this phrase even if the truncated content mentions agents or tools).
        *   Key: `modelInvocationOutput` → **Use exactly:**
            {{ "pt": "Resposta do modelo recebida", "en": "Received model response" }}
        *   Key: `observation` → **Use exactly:**
            {{ "pt": "Observando resultado da ação", "en": "Observing action result" }}
        *   Key: `agentCollaboratorInvocationInput` → **Use exactly:**
            {{ "pt": "Delegando tarefa", "en": "Delegating task" }}
        *   Key: `actionGroupInvocationInput` → **Use exactly:**
            {{ "pt": "Chamando tool", "en": "Calling tool" }}
        *   Key: `actionGroupInvocationOutput` → **Use exactly:**
            {{ "pt": "Saída da tool recebida", "en": "Received tool output" }}
        *   Key: `agentCollaboratorInvocationOutput` / `finalResponse` → **Use exactly:**
            {{ "pt": "Resultado do agente recebido", "en": "Received agent result" }}
    *   **If a match is found here (and it's NOT `rationale`): STOP. Your output MUST be ONLY the exact
        template phrase listed above.** Do NOT proceed to Priority 2 or Step 2. Do NOT use any
        information from the JSON content associated with the key, except as guided by Step 3 Rule 1 below.
    *   **If the first key found IS `rationale`:** Proceed directly to Step 2.

*   **Priority 2: If NO match in Priority 1 (or if `rationale` was matched), check directly inside `trace`:**
    *   Look for the **first key** directly in `trace` that matches:
        *   `guardrailTrace` → **Use exactly:**
            {{ "pt": "Aplicando guardrails", "en": "Applying guardrails" }}
    *   **If a match is found here: STOP. Your output MUST be ONLY the exact template phrase.**
        Do NOT proceed to Step 2.
    *   **If NO key was matched in Priority 1 or Priority 2:** Proceed to Step 2.

**Step 2: Generate Summary if NO Template Used OR if `rationale` was Matched**

*   This step applies ONLY if:
    *   The key `rationale` was the first match found in Step 1, OR
    *   NO key from the lists in Step 1 was found at all.
*   **If the key was `rationale`:** Generate a summary (≤ 10 words) based on the **content** of
    the `rationale` object. Start with "Thinking about..." or "Pensando sobre...". Briefly explain
    *what* is being thought about (e.g., "Thinking about user query", "Pensando sobre qual tool usar").
*   **If NO key was matched:** Craft a generic summary sentence (≤ 10 words) describing the overall
    action, starting with a suitable gerund/verb.

**Step 3: Final Output Rules (Apply AFTER determining the sentence in Step 1 or 2)**

1.  **Add Context (If Applicable):** If using a template phrase like "Delegating task", "Calling tool",
    or similar (from Step 1), you MAY add the specific agent name or tool name *after* the phrase
    if it's clearly identifiable in the JSON and fits within the word limit.
2.  Do **not** expose technical details (model names, architectures, language codes, etc.).
3.  The final sentence MUST NOT end with a period or any other punctuation mark.
4.  **CRITICAL:** Your *entire* response MUST consist of **ONLY** the single summary sentence
    determined above. **ABSOLUTELY NO** `<thinking>` tags, explanations, or any other text."""

    prompt += f"""

JSON trace to summarize:
```json
{trace_data_str}
```"""

    return prompt


def _update_trace_summary(language: str, trace_data: dict):
    prompt = _get_summary_prompt(language=language, trace_data=trace_data)
    client = OpenAI()
    if settings.TRACE_SUMMARY_DELAY:
        time.sleep(3)

    response = client.chat.completions.create(
        model="gpt-4.1-nano", temperature=0, max_tokens=100, messages=[{"role": "user", "content": prompt}]
    )

    summary = response.choices[0].message.content

    return summary


@observer("inline_trace_observers")
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
        **kwargs,
    ):
        # TODO: Fix circular import
        from nexus.projects.websockets.consumers import send_preview_message_to_websocket

        if not preview:
            return

        try:
            # Determine which trace data to use
            trace_data = inline_traces if inline_traces is not None else event_content

            if not trace_data:
                logging.warning("No trace data provided to SummaryTracesObserver")
                return

            # serialize datetime objects to string and deserialize to dict
            trace_data_str = json.dumps(trace_data, default=str)
            trace_data_str = json.loads(trace_data_str)
            trace_data_str.pop("callerChain", None)

            if user_email and project_uuid and session_id:
                send_preview_message_to_websocket(
                    project_uuid=str(project_uuid),
                    user_email=user_email,
                    message_data={"type": "trace_update", "trace": trace_data_str, "session_id": session_id},
                )

        except Exception as e:
            logging.error(f"Error getting trace summary: {str(e)}")
            return "Processing your request now"


@observer("inline_trace_observers_async", manager="async")
class AsyncSummaryTracesObserver(EventObserver):
    """
    Async version of SummaryTracesObserver for async contexts.
    """

    async def perform(
        self,
        language="en",
        event_content=None,
        inline_traces=None,
        preview=False,
        project_uuid=None,
        user_email=None,
        session_id=None,
        **kwargs,
    ):
        # TODO: Fix circular import
        from nexus.projects.websockets.consumers import send_preview_message_to_websocket_async

        if not preview:
            return

        try:
            trace_data = inline_traces if inline_traces is not None else event_content

            if not trace_data:
                logging.warning("No trace data provided to AsyncSummaryTracesObserver")
                return

            trace_data_str = json.dumps(trace_data, default=str)
            trace_data_str = json.loads(trace_data_str)
            trace_data_str.pop("callerChain", None)

            if user_email and project_uuid and session_id:
                await send_preview_message_to_websocket_async(
                    project_uuid=str(project_uuid),
                    user_email=user_email,
                    message_data={"type": "trace_update", "trace": trace_data_str, "session_id": session_id},
                )

        except Exception as e:
            logging.error(f"Error getting trace summary: {str(e)}")
            return "Processing your request now"
