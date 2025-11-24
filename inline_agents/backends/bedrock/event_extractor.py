import json
import logging

import sentry_sdk

from inline_agents.data_lake.event_service import EventExtractor

logger = logging.getLogger(__name__)


class BedrockEventExtractor(EventExtractor):
    """Extracts events from Bedrock trace format."""

    def extract_events(self, trace_data: dict) -> list[dict]:
        """Extract events from Bedrock trace format."""
        orchestration_trace = trace_data.get("trace", {}).get("orchestrationTrace", {})
        action_group_data = orchestration_trace.get("observation", {}).get("actionGroupInvocationOutput", {})

        if not action_group_data.get("text"):
            return []

        try:
            event_data = json.loads(action_group_data.get("text"))
        except (json.JSONDecodeError, TypeError) as e:
            project_uuid = trace_data.get("project_uuid", "unknown")
            contact_urn = trace_data.get("contact_urn", "unknown")
            logger.warning(
                f"Failed to parse action group response as JSON: {str(e)}. "
                f"Project: {project_uuid}, Contact: {contact_urn}"
            )
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_context(
                "json_parse_error", {"text": action_group_data.get("text", "")[:500], "contact_urn": contact_urn}
            )
            sentry_sdk.capture_exception(e)
            return []

        if isinstance(event_data, dict):
            return event_data.get("events", [])
        return []

    def get_agent_identifier(self, trace_data: dict) -> str:
        """Get collaborator name from Bedrock trace data."""
        return trace_data.get("collaborator_name", "")
