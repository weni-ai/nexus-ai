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


class Team(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    project_uuid = models.UUIDField()


class Agent(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    name = models.CharField(max_length=255)
    is_official = models.BooleanField(default=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)


class IntegratedAgent(models.Model):
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('agent', 'team')


class Version(models.Model):
    version = models.PositiveIntegerField()
    skills = models.JSONField()
    display_skills = ArrayField(models.JSONField())
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE)
    created_on = models.DateTimeField(auto_now_add=True)
