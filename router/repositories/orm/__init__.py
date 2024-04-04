from __future__ import absolute_import, unicode_literals
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")

django.setup()


from router.repositories import Repository

from django.db import reset_queries, close_old_connections
from django.dispatch import Signal


message_started = Signal()
message_finished = Signal()

message_started.connect(reset_queries)
message_started.connect(close_old_connections)
message_finished.connect(close_old_connections)

from nexus.projects.models import Project
from django.db import connections


class ProjectORMRepository(Repository):
    def __init__(self) -> None:
        self.check_connection()

    def check_connection(self):
        message_started.send(sender=self)
        try:
            db_conn = connections['default']
            db_conn.cursor()
        finally:
            message_finished.send(sender=self)

    def get(self, uuid: str):
        return Project.objects.get(uuid=uuid)

    def get_all(self):
        return Project.objects.all()[::1]
    
    def add(self):
        return super().add()

    def update(self, uuid: str):
        return super().update(uuid)
    
    def delete(self, uuid: str):
        return super().delete(uuid)


class FlowsORMRepository(Repository):
    ...