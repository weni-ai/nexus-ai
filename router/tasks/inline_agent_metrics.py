"""Prometheus metrics for start_inline_agents latency (Phase 0)."""

from prometheus_client import Counter, Histogram

# Celery broker / worker timing (wall clock, seconds)
INLINE_AGENT_BROKER_QUEUE_WAIT_SECONDS = Histogram(
    "inline_agent_broker_queue_wait_seconds",
    "Time from Celery publish to task prerun (broker dequeue + worker scheduling)",
    labelnames=("project_uuid",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

INLINE_AGENT_WORKER_SCHEDULING_DELAY_SECONDS = Histogram(
    "inline_agent_worker_scheduling_delay_seconds",
    "Time from worker task_received to task prerun",
    labelnames=("project_uuid",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0),
)

INLINE_AGENT_ROUTER_TO_ENQUEUE_SECONDS = Histogram(
    "inline_agent_router_to_enqueue_seconds",
    "Time from HTTP router received_at to Celery publish (enqueued_at)",
    labelnames=("project_uuid",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0),
)

# In-task phases (perf_counter, seconds)
INLINE_AGENT_PHASE_DURATION_SECONDS = Histogram(
    "inline_agent_phase_duration_seconds",
    "Duration of a processing phase inside start_inline_agents",
    labelnames=("phase", "project_uuid"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

INLINE_AGENT_TURN_DURATION_SECONDS = Histogram(
    "inline_agent_turn_duration_seconds",
    "Total start_inline_agents execution time (task prerun to finish)",
    labelnames=("status", "project_uuid"),
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 180.0, 300.0, 360.0),
)

INLINE_AGENT_CACHE_ACCESS_TOTAL = Counter(
    "inline_agent_cache_access_total",
    "Cache get attempts during pre-generation",
    labelnames=("cache_type", "hit", "project_uuid"),
)

INLINE_AGENT_ERRORS_TOTAL = Counter(
    "inline_agent_errors_total",
    "start_inline_agents failures by last completed phase",
    labelnames=("phase", "project_uuid"),
)

INLINE_AGENT_TURN_MISSING_PROJECT_UUID_TOTAL = Counter(
    "inline_agent_turn_missing_project_uuid_total",
    "Turns where project_uuid was missing or invalid (latency histograms skipped)",
)
