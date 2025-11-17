from inline_agents.data_lake.event_service import EventExtractor


class OpenAIEventExtractor(EventExtractor):
    """Extracts events from OpenAI format (events are already a list)."""

    def __init__(self, event_data: list, agent_name: str = ""):
        self.event_data = event_data
        self.agent_name = agent_name

    def extract_events(self, trace_data: dict) -> list[dict]:
        """Return events directly (already in list format for OpenAI)."""
        # Filter out non-dict items (e.g., strings) to prevent errors
        return [event for event in self.event_data if isinstance(event, dict)]

    def get_agent_identifier(self, trace_data: dict) -> str:
        """Get agent name from OpenAI trace data."""
        return self.agent_name
