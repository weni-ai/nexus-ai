from uuid import uuid4
from django.db import models
from django.contrib.postgres.fields import ArrayField

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


class Agent(models.Model):
    uuid = models.UUIDField(default=uuid4)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    is_official = models.BooleanField(default=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="inline_agents")
    instruction = models.TextField()
    collaboration_instructions = models.TextField()
    foundation_model = models.CharField(max_length=255)

    @property
    def current_version(self):
        return self.versions.order_by('created_on').last()


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


class ContactField(models.Model):
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="inline_contact_fields")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="inline_contact_fields")
    key = models.CharField(max_length=255)
    value_type = models.CharField(max_length=255)
