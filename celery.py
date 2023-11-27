from __future__ import absolute_import, unicode_literals
import os
import sys

from celery import Celery, schedules

from nexus import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")

app = Celery("nexus-ai")
app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)
