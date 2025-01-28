from typing import Dict
from uuid import uuid4

from django.db import models
from nexus.projects.models import Project
from nexus.db.models import BaseModel


class Agent(BaseModel):
    external_id = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    display_name = models.CharField(max_length=255)
    model = models.CharField(max_length=255)
    is_official = models.BooleanField(default=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    metadata = models.JSONField(default=dict)
    description = models.CharField(max_length=255, null=True)

    @property
    def bedrock_agent_name(self):
        return f"{self.slug}-project-{self.project.uuid}"


class Team(models.Model):
    external_id = models.CharField(max_length=255, help_text="Supervisor ID")
    project = models.OneToOneField(Project, on_delete=models.CASCADE)
    metadata = models.JSONField(default=dict)

    def update_metadata(self, metadata: Dict[str, str]):
        self.metadata.update(metadata)
        self.save()

    @property
    def current_version(self):
        return self.versions.last()

    @property
    def list_versions(self):
        return self.versions.order_by()


class TeamVersion(BaseModel):
    uuid = models.UUIDField(default=uuid4, editable=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="versions")
    alias_id = models.CharField(max_length=255, help_text="Supervisor alias ID")
    alias_name = models.CharField(max_length=255, help_text="Supervisor alias name", null=True)
    metadata = models.JSONField(default=dict)


class ActiveAgent(BaseModel):
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    is_official = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict)


class AgentSkills(BaseModel):
    display_name = models.CharField(max_length=255)
    unique_name = models.CharField(max_length=255, unique=True)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="agent_skills")
    skill = models.JSONField(default=dict)
