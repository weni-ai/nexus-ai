"""Mock service for data lake events - useful for testing and local development."""

import logging
from typing import Any, Dict, List

from inline_agents.data_lake.event_service import DataLakeEventService

logger = logging.getLogger(__name__)


class MockDataLakeEventService(DataLakeEventService):
    """Mock service that stores events instead of sending them to data lake.

    Useful for:
    - Unit testing without requiring data lake infrastructure
    - Local development without starting Celery/data lake services
    - Inspecting events that would be sent

    Usage:
        # In tests
        mock_service = MockDataLakeEventService()
        adapter._event_service = mock_service

        # After operations
        assert len(mock_service.sent_events) == 1
        assert mock_service.sent_events[0]["key"] == "weni_csat"
    """

    def __init__(self):
        """Initialize mock service with empty event storage."""
        self.sent_events: List[Dict[str, Any]] = []
        self.sent_events_sync: List[Dict[str, Any]] = []
        self.sent_events_async: List[Dict[str, Any]] = []

        # Create a mock task object that can be called both sync and async
        mock_task = self._create_mock_task()
        super().__init__(send_data_lake_event_task=mock_task)

    def _create_mock_task(self):
        """Create a mock task object that supports both sync and async calls."""
        service_ref = self

        class MockTask:
            def __call__(self, event_data: dict):
                """Handle sync calls (no .delay())."""
                logger.debug(f"[MOCK] Would send event to data lake (sync): {event_data.get('key', 'unknown')}")
                service_ref.sent_events.append(event_data)
                service_ref.sent_events_sync.append(event_data)
                return {"status": "mocked", "event": event_data}

            def delay(self, event_data: dict):
                """Handle async calls (.delay())."""
                logger.debug(f"[MOCK] Would send event to data lake (async): {event_data.get('key', 'unknown')}")
                service_ref.sent_events.append(event_data)
                service_ref.sent_events_async.append(event_data)
                return {"status": "mocked", "event": event_data}

        return MockTask()

    def clear_events(self):
        """Clear all stored events. Useful for test cleanup."""
        self.sent_events.clear()
        self.sent_events_sync.clear()
        self.sent_events_async.clear()

    def get_events_by_key(self, key: str) -> List[Dict[str, Any]]:
        """Get all events with a specific key."""
        return [event for event in self.sent_events if event.get("key") == key]

    def get_events_by_project(self, project_uuid: str) -> List[Dict[str, Any]]:
        """Get all events for a specific project."""
        return [event for event in self.sent_events if event.get("project") == project_uuid]

    def has_event(self, key: str, project_uuid: str = None) -> bool:
        """Check if an event with the given key (and optionally project) was sent."""
        events = self.get_events_by_key(key)
        if project_uuid:
            events = [e for e in events if e.get("project") == project_uuid]
        return len(events) > 0
