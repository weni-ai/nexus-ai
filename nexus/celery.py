import logging
import os
import sys
from typing import Optional

import logfire
import nest_asyncio
from celery import Celery, schedules
from celery.signals import worker_process_init, worker_ready
from django.conf import settings
from langfuse import get_client

logger = logging.getLogger(__name__)

# Per-process: prefork pool children must run instrument_openai_agents() after fork; the
# main worker process only receives worker_ready. Solo pool has no children — worker_ready is enough.
_logfire_openai_agents_instrumented_pid: Optional[int] = None

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")

app = Celery("nexus")
app.config_from_object("django.conf:settings", namespace="CELERY")

rate_limit = settings.INVOKE_AGENTS_RATE_LIMIT


app.conf.task_routes = {
    "router.tasks.invoke.start_inline_agents": {"queue": "inline-agents"},
}

app.conf.task_annotations = {"router.tasks.invoke.start_inline_agents": {"rate_limit": rate_limit}}

app.conf.imports = ("nexus.usecases.intelligences.lambda_usecase",)


app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

task_create_missing_queues = True

app.conf.event_serializer = "json"
app.conf.task_serializer = "json"
app.conf.result_serializer = "json"
app.conf.accept_content = ["application/json"]
app.conf.worker_disable_prefetch = True

app.conf.beat_schedule = {
    "log_cleanup_routine": {"task": "log_cleanup_routine", "schedule": schedules.crontab(hour=23, minute=0)},
    "delete_old_activities": {"task": "delete_old_activities", "schedule": schedules.crontab(hour=23, minute=0)},
    "healthcheck": {"task": "healthcheck", "schedule": schedules.crontab(minute="*/1")},
    "classification_healthcheck": {"task": "classification_healthcheck", "schedule": schedules.crontab(minute="*/5")},
}

if "test" in sys.argv or getattr(settings, "CELERY_ALWAYS_EAGER", False):
    from celery import current_app

    def send_task(name, args: tuple = (), kwargs: Optional[dict] = None, **opts):  # pragma: needs cover
        if kwargs is None:
            kwargs = {}
        task = current_app.tasks[name]
        return task.apply(args, kwargs, **opts)

    current_app.send_task = send_task


nest_asyncio.apply()


def _configure_logfire_and_instrument_openai_agents() -> None:
    """Configure Logfire and instrument OpenAI Agents once per OS process.

    Celery prefork runs tasks in forked pool workers. worker_ready runs on the parent
    consumer; pool children need their own instrumentation after fork.
    """
    global _logfire_openai_agents_instrumented_pid

    logfire.configure(
        service_name="openai-agents",
        send_to_logfire=False,
    )

    if not settings.ENABLE_LOGFIRE_OPENAI_AGENTS:
        return

    if _logfire_openai_agents_instrumented_pid == os.getpid():
        return

    logfire.instrument_openai_agents()
    _logfire_openai_agents_instrumented_pid = os.getpid()


@worker_process_init.connect
def setup_logfire_in_pool_worker(sender, **kwargs) -> None:
    """Prefork pool child: ensure Logfire instruments this process (tasks run here)."""
    _configure_logfire_and_instrument_openai_agents()


@worker_ready.connect
def setup_logfire_and_langfuse(sender, **kwargs):
    _configure_logfire_and_instrument_openai_agents()

    if settings.ENABLE_LOGFIRE_OPENAI_AGENTS:
        try:
            langfuse = get_client()
            if langfuse.auth_check():
                logger.info("Langfuse client is authenticated and ready!")
            else:
                logger.error("Langfuse authentication failed. Check credentials and host.")
        except Exception:
            logger.exception("Failed to connect to Langfuse, worker will continue without it.")
