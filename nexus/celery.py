import logging
import os
import sys
from typing import Optional

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")

from nexus.celery_otel_bootstrap import (
    bootstrap_celery_otel_before_django,
    configure_logfire_openai_agents_otel,
)

# Before Django loads (django.setup installs a concrete OTEL TracerProvider early).
bootstrap_celery_otel_before_django()

import nest_asyncio  # noqa: E402
from celery import Celery, schedules  # noqa: E402
from celery.signals import worker_process_init, worker_ready  # noqa: E402
from django.conf import settings  # noqa: E402
from langfuse import get_client  # noqa: E402

logger = logging.getLogger(__name__)

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

    Celery prefork runs tasks in forked pool workers: pool children need their own
    instrumentation after fork (PID changes).
    """
    configure_logfire_openai_agents_otel(settings.ENABLE_LOGFIRE_OPENAI_AGENTS)


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
