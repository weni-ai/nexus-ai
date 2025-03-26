from typing import Dict
from uuid import uuid4

from django.db import models
from nexus.projects.models import Project
from nexus.db.models import BaseModel
from nexus.agents.encryption import decrypt_value
from nexus.agents.exceptions import (
    CredentialKeyInvalid,
    CredentialLabelInvalid,
    CredentialValueInvalid,
    CredentialPlaceholderInvalid,
    CredentialIsConfidentialInvalid,
)


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

    @property
    def current_version(self):
        return self.versions.last()

    @property
    def list_versions(self):
        return self.versions.order_by("created_at")

    def create_version(
        self,
        agent_alias_id: str,
        agent_alias_name: str,
        agent_alias_arn: str,
        agent_alias_version: str
    ):
        self.versions.create(
            alias_id=agent_alias_id,
            alias_name=agent_alias_name,
            metadata={
                "agent_alias": agent_alias_arn,
                "agent_alias_version": agent_alias_version,
            },
            created_by=self.created_by,
        )


class Credential(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="credentials")
    key = models.CharField(max_length=255, null=True)
    label = models.CharField(max_length=255)
    value = models.CharField(max_length=8192)
    placeholder = models.CharField(max_length=255, null=True)
    is_confidential = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict)
    agents = models.ManyToManyField(Agent)

    def clean(self):
        if not isinstance(self.key, str):
            raise CredentialKeyInvalid(field_name=self.key)
        if self.key and len(self.key) > 255:
            raise CredentialKeyInvalid.length_exceeded(field_name=self.key)

        if not isinstance(self.label, str) or not self.label:
            raise CredentialLabelInvalid(field_name=self.key)
        if len(self.label) > 255:
            raise CredentialLabelInvalid.length_exceeded(field_name=self.key)

        if not isinstance(self.value, str):
            raise CredentialValueInvalid(field_name=self.key)
        if len(self.value) > 8192:
            raise CredentialValueInvalid.length_exceeded(field_name=self.key)

        if self.placeholder is not None:
            if not isinstance(self.placeholder, str):
                raise CredentialPlaceholderInvalid(field_name=self.key)
            if len(self.placeholder) > 255:
                raise CredentialPlaceholderInvalid.length_exceeded(field_name=self.key)

        if not isinstance(self.is_confidential, bool):
            raise CredentialIsConfidentialInvalid(field_name=str(self.key))

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def decrypted_value(self):
        """Get the decrypted value of the credential"""
        if self.value:
            try:
                decrypted = decrypt_value(self.value)
                return decrypted
            except Exception as e:
                return self.value
        return self.value


class Team(models.Model):
    external_id = models.CharField(max_length=255, help_text="Supervisor ID")
    project = models.OneToOneField(Project, on_delete=models.CASCADE)
    metadata = models.JSONField(default=dict)

    human_support = models.BooleanField(default=False)
    human_support_prompt = models.TextField(null=True, blank=True)

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
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="active_agents")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="team_agents")
    is_official = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict)

    class Meta:
        unique_together = ("agent", "team")

    def __str__(self):
        return f"{self.agent.display_name} - {self.team.project} - {self.is_official}"


class AgentSkills(BaseModel):
    display_name = models.CharField(max_length=255)
    unique_name = models.CharField(max_length=255, unique=True)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="agent_skills")
    skill = models.JSONField(default=dict)


class AgentVersion(BaseModel):
    uuid = models.UUIDField(default=uuid4, editable=True)
    alias_id = models.CharField(max_length=255, help_text="Supervisor alias ID")
    alias_name = models.CharField(max_length=255, help_text="Supervisor alias name", null=True)
    metadata = models.JSONField(default=dict)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="versions")


class AgentSkillVersion(BaseModel):
    uuid = models.UUIDField(default=uuid4, editable=True)
    agent_skill = models.ForeignKey(AgentSkills, on_delete=models.CASCADE, related_name="versions")
    metadata = models.JSONField(default=dict)


class ContactField(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="contact_fields")
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="contact_fields")
    key = models.CharField(max_length=255)
    value_type = models.CharField(max_length=255)


class AgentMessage(models.Model):
    TRACES_BASE_PATH = "traces"

    uuid = models.UUIDField(default=uuid4, editable=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="agent_messages")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="agent_messages")
    user_text = models.TextField()
    agent_response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    contact_urn = models.CharField(max_length=255)
    session_id = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict)
    source = models.CharField(max_length=255)

    @property
    def trace_path(self):
        return f"{self.TRACES_BASE_PATH}/{self.project.uuid}/{self.uuid}.jsonl"
