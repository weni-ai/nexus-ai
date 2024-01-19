import uuid

from django.db import models

from nexus.intelligences.models import ContentBaseFile
from nexus.users.models import User


class TaskManager(models.Model):
    STATUS_WAITING = "waiting"
    STATUS_LOADING = "loading"
    STATUS_PROCESSING = "Processing"
    STATUS_SUCCESS = "success"
    STATUS_FAIL = "fail"

    STATUS_CHOICES = [
        (STATUS_LOADING, "Loading"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAIL, "Fail"),
        (STATUS_WAITING, "Wait")
    ]

    uuid = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    end_at = models.DateTimeField(null=True, blank=True)
    status = models.TextField(choices=STATUS_CHOICES, default=STATUS_WAITING)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="files")


class ContentBaseFileTaskManager(TaskManager):
    content_base_file = models.ForeignKey(ContentBaseFile, on_delete=models.CASCADE, related_name="upload_tasks", blank=True, null=True)

    def update_status(self, new_status):
        self.status = new_status
        self.save(update_fields=["status"])
