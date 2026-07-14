"""Enqueue start_inline_agents with router timing metadata."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from router.tasks.invoke import start_inline_agents


def _stamp_router_timestamps(message: Dict) -> Dict:
    payload = dict(message)
    now = time.time()
    payload.setdefault("router_received_at", now)
    payload.setdefault("inline_agent_enqueued_at", now)
    return payload


def enqueue_start_inline_agents(message: Optional[Dict] = None, **task_kwargs: Any):
    """Publish start_inline_agents with router_received_at when not already set."""
    queue = task_kwargs.pop("queue", None)

    if message is not None:
        payload = _stamp_router_timestamps(message)
        options: Dict[str, Any] = {"args": [payload], "kwargs": task_kwargs}
    else:
        payload = _stamp_router_timestamps(task_kwargs.pop("message", {}))
        task_kwargs["message"] = payload
        options = {"kwargs": task_kwargs}

    if queue:
        options["queue"] = queue

    return start_inline_agents.apply_async(**options)
