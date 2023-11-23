import uuid

from django.db import models

from nexus.intelligences.models import ContentBaseFile
from nexus.users.models import User

# deixar abstrata
# 
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
    end_at = models.DateTimeField()
    status = models.TextField(choices=STATUS_CHOICES, default=STATUS_WAITING)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name="files")


class ContentBaseFileUpload(TaskManager):
    content_base_file = models.ForeignKey(ContentBaseFile, on_delete=models.SET_NULL, related_name="upload_tasks")