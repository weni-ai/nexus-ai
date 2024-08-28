import uuid

from django.db import models

from nexus.intelligences.models import (
    ContentBaseFile,
    ContentBaseText,
    ContentBaseLink,
)
from nexus.users.models import User
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase


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

    status_map = {
        "STARTING": STATUS_LOADING,
        "IN_PROGRESS": STATUS_PROCESSING,
        "COMPLETE": STATUS_SUCCESS,
        "FAILED": STATUS_FAIL,
    }

    uuid = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    end_at = models.DateTimeField(null=True, blank=True)
    status = models.TextField(choices=STATUS_CHOICES, default=STATUS_WAITING)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="files")


class ContentBaseFileTaskManager(TaskManager):
    content_base_file = models.ForeignKey(ContentBaseFile, on_delete=models.CASCADE, related_name="upload_tasks", blank=True, null=True)
    ingestion_job_id = models.CharField(null=True)

    def update_status(self, new_status):
        self.status = new_status
        self.save(update_fields=["status"])

    @property
    def get_status(self):

        if self.ingestion_job_id:
            status = BedrockFileDatabase().get_bedrock_ingestion_status(self.ingestion_job_id)
            if self.status != self.status_map.get(status):
                self.update_status(status)

        return self.status


class ContentBaseTextTaskManager(TaskManager):
    content_base_text = models.ForeignKey(ContentBaseText, on_delete=models.CASCADE, related_name="upload_tasks", blank=True, null=True)
    file_url = models.URLField()
    file_name = models.CharField(max_length=255)

    def update_status(self, new_status):
        self.status = new_status
        self.save(update_fields=["status"])


class ContentBaseLinkTaskManager(TaskManager):
    content_base_link = models.ForeignKey(ContentBaseLink, on_delete=models.CASCADE, related_name="upload_tasks", blank=True, null=True)

    def update_status(self, new_status):
        self.status = new_status
        self.save(update_fields=["status"])
