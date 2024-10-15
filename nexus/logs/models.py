from uuid import uuid4

from django.db import models
from django.contrib.postgres.fields import ArrayField

from nexus.users.models import User
from nexus.projects.models import Project
from nexus.intelligences.models import ContentBase, Intelligence


class Message(models.Model):

    STATUS_CHOICES = (
        ("F", "fail"),
        ("P", "processing"),
        ("S", "success")
    )

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    text = models.TextField()
    contact_urn = models.CharField(max_length=255)
    status = models.CharField(
        max_length=1, choices=STATUS_CHOICES, default='P'
    )
    exception = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.status} - {self.contact_urn}"


class MessageLog(models.Model):
    message = models.OneToOneField(Message, on_delete=models.CASCADE)
    chunks = ArrayField(models.TextField(), null=True)
    prompt = models.TextField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True)
    content_base = models.ForeignKey(
        ContentBase, on_delete=models.CASCADE, null=True
    )
    classification = models.CharField(max_length=255, null=True)
    llm_model = models.CharField(max_length=255, null=True)
    llm_response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(null=True)
    source = models.CharField(max_length=255, null=True)

    groundedness_score = models.IntegerField(null=True)
    reflection_data = models.JSONField(null=True)

    def __str__(self) -> str:
        return f"{self.message}"


class RecentActivities(models.Model):

    ACTION_CHOICES = (
        ("C", "created"),
        ("U", "updated"),
        ("D", "deleted")
    )

    action_model = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    action_details = models.JSONField(null=True, blank=True)
    action_type = models.CharField(max_length=1, choices=ACTION_CHOICES)

    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    intelligence = models.ForeignKey(Intelligence, on_delete=models.CASCADE)

    def __str__(self) -> str:
        return f"{self.uuid} - {self.action_type}"
