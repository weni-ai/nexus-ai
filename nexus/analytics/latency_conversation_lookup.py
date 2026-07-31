"""Build nexus-conversations lookup hints from outlier rows."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

DEFAULT_LOOKUP_WINDOW_MINUTES = 5


def build_conversation_lookup(
    *,
    project_uuid: str,
    contact_urn: str,
    turn_finished_at: datetime,
    turn_id: Optional[str] = None,
    window_minutes: int = DEFAULT_LOOKUP_WINDOW_MINUTES,
) -> Dict[str, Any]:
    start = turn_finished_at - timedelta(minutes=window_minutes)
    end = turn_finished_at + timedelta(minutes=window_minutes)
    payload: Dict[str, Any] = {
        "service": "nexus-conversations",
        "project_uuid": str(project_uuid),
        "contact_urn": contact_urn,
        "start_date": start.isoformat().replace("+00:00", "Z"),
        "end_date": end.isoformat().replace("+00:00", "Z"),
    }
    if turn_id:
        payload["correlation_id"] = turn_id
    return payload
