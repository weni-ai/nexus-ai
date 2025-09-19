from uuid import uuid4
from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.conf import settings

from nexus.agents.encryption import decrypt_value
from nexus.agents.exceptions import (
    CredentialKeyInvalid,
    CredentialLabelInvalid,
    CredentialValueInvalid,
    CredentialPlaceholderInvalid,
    CredentialIsConfidentialInvalid,
)
from nexus.projects.models import Project


class Guardrail(models.Model):
    identifier = models.CharField(max_length=255)
    version = models.PositiveIntegerField()
    created_on = models.DateTimeField(auto_now_add=True)
    changelog = models.TextField()
    current_version = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.identifier} - {self.version}"


class Agent(models.Model):
    VTEX_APP = "VTEX_APP"
    PLATFORM = "PLATFORM"

    AGENT_TYPE_CHOICES = (
        (VTEX_APP, "VTEX App"),
        (PLATFORM, "Platform"),
    )

    uuid = models.UUIDField(default=uuid4)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    is_official = models.BooleanField(default=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="inline_agents")
    instruction = models.TextField()
    collaboration_instructions = models.TextField()
    foundation_model = models.CharField(max_length=255)  # will be deprecated
    backend_foundation_models = models.JSONField(default=dict)
    source_type = models.CharField(max_length=255, choices=AGENT_TYPE_CHOICES, default=PLATFORM)

    @property
    def current_version(self):
        return self.versions.order_by('created_on').last()

    def __get_default_value_fallback(self, agents_backend):
        if agents_backend == "BedrockBackend":
            return self.foundation_model
        elif agents_backend == "OpenAIBackend":
            return settings.OPENAI_AGENTS_FOUNDATION_MODEL

    def current_foundation_model(self, agents_backend, project = None):
        if not project:
            project = self.project

        default_value = self.__get_default_value_fallback(agents_backend)

        if project.default_collaborators_foundation_model:
            return project.default_collaborators_foundation_model
        return self.backend_foundation_models.get(agents_backend, default_value)


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


class AgentCredential(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="inline_credentials")
    key = models.CharField(max_length=255, null=True)
    label = models.CharField(max_length=255)
    value = models.CharField(max_length=8192, default="")
    placeholder = models.CharField(max_length=255, null=True)
    is_confidential = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict)
    agents = models.ManyToManyField(Agent)

    class Meta:
        unique_together = ('project', 'key')

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
            except Exception:
                return self.value
        return self.value


class ContactField(models.Model):
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="inline_contact_fields")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="inline_contact_fields")
    key = models.CharField(max_length=255)
    value_type = models.CharField(max_length=255)


class InlineAgentMessage(models.Model):
    TRACES_BASE_PATH = "traces"

    created_at = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(default=uuid4, editable=True)
    text = models.TextField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="inline_agent_messages")
    session_id = models.CharField(max_length=255)
    contact_urn = models.CharField(max_length=255)
    source_type = models.CharField(max_length=255)
    source = models.CharField(max_length=255)

    @property
    def trace_path(self):
        return f"{self.TRACES_BASE_PATH}/{self.project.uuid}/{self.uuid}.jsonl"

    class Meta:
        indexes = [
            models.Index(fields=["project", "created_at", "contact_urn"]),
        ]


class InlineAgentsConfiguration(models.Model):
    # TODO: Move inline agents configuration from project model to this model
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="inline_agent_configurations")
    agents_backend = models.CharField(max_length=100)
    default_instructions_for_collaborators = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Project: {self.project.name} - Agents backend: {self.agents_backend}"

    class Meta:
        verbose_name = "Inline agents configurations for a project"
        verbose_name_plural = "Inline agents configurations for a project"
        unique_together = ('project', 'agents_backend')
