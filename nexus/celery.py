from __future__ import absolute_import, unicode_literals
import os
import sys

from celery import Celery, schedules

from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")

app = Celery("nexus")
app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

task_create_missing_queues = True

app.conf.event_serializer = 'json'
app.conf.task_serializer = 'json'
app.conf.result_serializer = 'json'
app.conf.accept_content = ['application/json']

app.conf.beat_schedule = {
    "log_cleanup_routine": {
        "task": "log_cleanup_routine",
        "schedule": schedules.crontab(hour=23, minute=0)
    },
    "delete_old_activities": {
        "task": "delete_old_activities",
        "schedule": schedules.crontab(hour=23, minute=0)
    },
    "healthcheck": {
        "task": "healthcheck",
        "schedule": schedules.crontab(minute="*/1")
    },
    "classification_healthcheck": {
        "task": "classification_healthcheck",
        "schedule": schedules.crontab(minute="*/5")
    },
}

if "test" in sys.argv or getattr(settings, "CELERY_ALWAYS_EAGER", False):
    from celery import current_app

    def send_task(name, args=(), kwargs={}, **opts):  # pragma: needs cover
        task = current_app.tasks[name]
        return task.apply(args, kwargs, **opts)

    current_app.send_task = send_task
