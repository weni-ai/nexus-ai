from uuid import uuid4

from django.db import models
from django.contrib.postgres.fields import ArrayField

from nexus.projects.models import Project
from nexus.intelligences.models import ContentBase


class Message(models.Model):

    STATUS_CHOICES = (
        ("F", "fail"),
        ("P", "processing"),
        ("S", "success")
    )

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    text = models.TextField()
    contact_urn = models.CharField(max_length=255)
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default='P')
    exception = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.status} - {self.contact_urn}"


class MessageLog(models.Model):
    message = models.OneToOneField(Message, on_delete=models.CASCADE)
    chunks = ArrayField(models.TextField(), null=True)
    prompt = models.TextField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True)
    content_base = models.ForeignKey(ContentBase, on_delete=models.CASCADE, null=True)
    classification = models.CharField(max_length=255, null=True)
    llm_model = models.CharField(max_length=255, null=True)
    llm_response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(null=True)

    def __str__(self) -> str:
        return f"{self.message}"
