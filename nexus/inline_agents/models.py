from uuid import uuid4
from django.db import models
from django.contrib.postgres.fields import ArrayField

from nexus.projects.models import Project


class Guardrail(models.Model):
    identifier = models.CharField(max_length=255)
    version = models.PositiveIntegerField()
    created_on = models.DateTimeField(auto_now_add=True)
    changelog = models.TextField()
    current_version = models.BooleanField(default=True)


class Agent(models.Model):
    uuid = models.UUIDField(default=uuid4)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    is_official = models.BooleanField(default=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="inline_agents")
    instruction = models.TextField()
    collaboration_instructions = models.TextField()
    foundation_model = models.CharField(max_length=255)


class IntegratedAgent(models.Model):
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="integrated_agents")
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('agent', 'project')


class Version(models.Model):
    skills = ArrayField(models.JSONField())
    display_skills = ArrayField(models.JSONField())
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="versions")
    created_on = models.DateTimeField(auto_now_add=True)
