import os
import sys
from typing import Optional

import logfire
import nest_asyncio
from celery import Celery, schedules
from django.conf import settings
from langfuse import get_client

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

logfire.configure(
    service_name="openai-agents",
    send_to_logfire=False,
)

enable_instrumentation = os.environ.get("ENABLE_LOGFIRE_OPENAI_AGENTS") == "1"
if enable_instrumentation:
    logfire.instrument_openai_agents()
    langfuse = get_client()

    if langfuse.auth_check():
        print("Langfuse client is authenticated and ready!")
    else:
        print("Authentication failed. Please check your credentials and host.")
