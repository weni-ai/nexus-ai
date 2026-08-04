"""Celery signals for start_inline_agents latency headers (Phase 0).

Lives under nexus/ (not router.tasks) so nexus.celery can import it before
Django apps are ready — router.tasks.__init__ pulls in ORM-dependent modules.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional
from uuid import UUID

from celery.signals import before_task_publish, task_prerun, task_received

from nexus.inline_agent_latency_headers import (
    HEADER_ENQUEUED_AT,
    HEADER_PROJECT_UUID,
    HEADER_RECEIVED_AT,
    HEADER_STARTED_AT,
    START_INLINE_AGENTS_TASK_NAME,
)

logger = logging.getLogger(__name__)


def _parse_project_uuid_from_message(message: Any) -> Optional[str]:
    if not isinstance(message, dict):
        return None
    raw = message.get("project_uuid")
    if raw is None:
        return None
    try:
        return str(UUID(str(raw)))
    except (ValueError, TypeError, AttributeError):
        return None


def _ensure_headers(headers: Optional[Dict]) -> Dict:
    return headers if headers is not None else {}


@before_task_publish.connect
def stamp_inline_agent_publish_headers(sender=None, body=None, headers=None, **kwargs) -> None:
    if sender != START_INLINE_AGENTS_TASK_NAME:
        return

    if headers is None:
        return

    headers[HEADER_ENQUEUED_AT] = str(time.time())

    try:
        args = body[0] if body else ()
        task_kwargs = body[1] if body and len(body) > 1 else {}
        message = args[0] if args else task_kwargs.get("message", {})
        project_uuid = _parse_project_uuid_from_message(message)
        if project_uuid:
            headers[HEADER_PROJECT_UUID] = project_uuid
    except (IndexError, TypeError, AttributeError):
        logger.debug("Could not extract project_uuid for Celery publish headers", exc_info=True)


@task_received.connect
def stamp_inline_agent_received_at(request=None, **kwargs) -> None:
    if request is None or request.name != START_INLINE_AGENTS_TASK_NAME:
        return
    hdrs = _ensure_headers(getattr(request, "headers", None))
    hdrs[HEADER_RECEIVED_AT] = str(time.time())
    request.headers = hdrs


@task_prerun.connect
def stamp_inline_agent_started_at(task_id=None, task=None, **kwargs) -> None:
    if task is None or task.name != START_INLINE_AGENTS_TASK_NAME:
        return
    hdrs = _ensure_headers(getattr(task.request, "headers", None))
    hdrs[HEADER_STARTED_AT] = str(time.time())
    task.request.headers = hdrs
