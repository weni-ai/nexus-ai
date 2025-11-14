from inline_agents.data_lake.event_service import EventExtractor


class OpenAIEventExtractor(EventExtractor):
    """Extracts events from OpenAI format (events are already a list)."""

    def __init__(self, event_data: list, agent_name: str = ""):
        self.event_data = event_data
        self.agent_name = agent_name

    def extract_events(self, trace_data: dict) -> list[dict]:
        """Return events directly (already in list format for OpenAI)."""
        return self.event_data

    def get_agent_identifier(self, trace_data: dict) -> str:
        """Get agent name from OpenAI trace data."""
        return self.agent_name
