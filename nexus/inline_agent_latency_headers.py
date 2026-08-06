"""Celery header keys for inline agent latency tracing."""

START_INLINE_AGENTS_TASK_NAME = "router.tasks.invoke.start_inline_agents"

HEADER_ENQUEUED_AT = "inline_agent_enqueued_at"
HEADER_RECEIVED_AT = "inline_agent_received_at"
HEADER_STARTED_AT = "inline_agent_started_at"
HEADER_PROJECT_UUID = "inline_agent_project_uuid"
