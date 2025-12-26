from uuid import uuid4

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from nexus.agents.encryption import decrypt_value
from nexus.agents.exceptions import (
    CredentialIsConfidentialInvalid,
    CredentialKeyInvalid,
    CredentialLabelInvalid,
    CredentialPlaceholderInvalid,
    CredentialValueInvalid,
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
    foundation_model = models.CharField(max_length=255, null=True, blank=True, default="")  # will be deprecated
    backend_foundation_models = models.JSONField(default=dict)
    source_type = models.CharField(max_length=255, choices=AGENT_TYPE_CHOICES, default=PLATFORM)
    agent_type = models.ForeignKey(
        "AgentType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agents",
    )
    category = models.ForeignKey(
        "AgentCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agents",
    )
    group = models.ForeignKey("AgentGroup", on_delete=models.SET_NULL, null=True, blank=True, related_name="agents")
    systems = models.ManyToManyField("AgentSystem", blank=True, related_name="agents")

    variant = models.CharField(max_length=100, null=True, blank=True)
    capabilities = models.JSONField(default=list, null=True, blank=True)
    policies = models.JSONField(default=dict, null=True, blank=True)
    tooling = models.JSONField(default=dict, null=True, blank=True)
    catalog = models.JSONField(default=dict, null=True, blank=True)

    def __str__(self):
        return self.name

    @property
    def current_version(self):
        return self.versions.order_by("created_on").last()

    def __get_default_value_fallback(self, agents_backend):
        if agents_backend == "BedrockBackend":
            return self.foundation_model
        elif agents_backend == "OpenAIBackend":
            return settings.OPENAI_AGENTS_FOUNDATION_MODEL

    def current_foundation_model(self, agents_backend, project=None):
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
    metadata = models.JSONField(default=dict, null=True, blank=True)

    class Meta:
        unique_together = ("agent", "project")

    def __str__(self):
        return f"{self.agent.name} - {self.project}"


class Version(models.Model):
    skills = ArrayField(models.JSONField())
    display_skills = ArrayField(models.JSONField())
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="versions")
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Version for {self.agent.name} - {self.created_on}"


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
        unique_together = ("project", "key")

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

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

    def __str__(self):
        return f"{self.key}: {self.value_type}"


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

    class Meta:
        indexes = [
            models.Index(fields=["project", "created_at", "contact_urn"]),
        ]

    def __str__(self):
        return f"InlineAgentMessage - {self.contact_urn}"

    @property
    def trace_path(self):
        return f"{self.TRACES_BASE_PATH}/{self.project.uuid}/{self.uuid}.jsonl"


class InlineAgentsConfiguration(models.Model):
    valid_voices = ["alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer", "verse"]
    # TODO: Move inline agents configuration from project model to this model
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="inline_agent_configurations")
    agents_backend = models.CharField(max_length=100)
    default_instructions_for_collaborators = models.TextField(null=True, blank=True)
    audio_orchestration = models.BooleanField(default=False)
    audio_orchestration_voice = models.CharField(null=True, blank=True, default="shimmer")

    class Meta:
        verbose_name = "Inline agents configurations for a project"
        verbose_name_plural = "Inline agents configurations for a project"
        unique_together = ("project", "agents_backend")

    def __str__(self):
        return f"Project: {self.project.name} - Agents backend: {self.agents_backend}"

    def set_audio_orchestration_voice(self, voice: str):
        if voice not in self.valid_voices:
            raise ValueError
        self.audio_orchestration_voice = voice
        self.save()

    def set_audio_orchestration(self, activate: bool, voice: str = None):
        if voice:
            try:
                self.set_audio_orchestration_voice(voice)
            except ValueError:
                raise

        self.audio_orchestration = activate
        self.save()


class AgentGroup(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    shared_config = models.JSONField(default=dict)

    def __str__(self):
        return self.name


class AgentSystem(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    metadata = models.JSONField(default=dict)

    def __str__(self):
        return self.name


class AgentType(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class AgentCategory(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class MCP(models.Model):
    """Micro-Capability Package - Represents a specific capability configuration for an agent/system combination"""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    agent = models.ForeignKey(
        Agent,
        on_delete=models.CASCADE,
        related_name="mcps",
        limit_choices_to={"is_official": True},
    )
    system = models.ForeignKey(
        AgentSystem,
        on_delete=models.CASCADE,
        related_name="mcps",
    )
    order = models.PositiveIntegerField(default=0, help_text="Order for display")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("agent", "system", "name")
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.agent.slug} - {self.system.slug} - {self.name}"


class MCPConfigOption(models.Model):
    """Configuration options for an MCP (e.g., REGIONALIZATION checkbox, PRICE_SOURCE select)"""

    CHECKBOX = "CHECKBOX"
    SELECT = "SELECT"
    TEXT = "TEXT"
    NUMBER = "NUMBER"
    SWITCH = "SWITCH"
    RADIO = "RADIO"

    TYPE_CHOICES = (
        (CHECKBOX, "Checkbox"),
        (SELECT, "Select"),
        (TEXT, "Text"),
        (NUMBER, "Number"),
        (SWITCH, "Switch"),
        (RADIO, "Radio"),
    )

    mcp = models.ForeignKey(MCP, on_delete=models.CASCADE, related_name="config_options")
    name = models.CharField(max_length=255, help_text="Internal name (e.g., REGIONALIZATION)")
    label = models.CharField(max_length=255, help_text="Display label")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=SELECT)
    options = models.JSONField(
        default=list,
        help_text="For SELECT/RADIO type: [{'name': 'Display', 'value': 'internal'}]",
    )
    default_value = models.JSONField(
        default=None,
        null=True,
        blank=True,
        help_text="Default value. Type depends on field type (str, int, bool, etc.)",
    )
    order = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField(default=False)

    class Meta:
        unique_together = ("mcp", "name")
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.mcp} - {self.label}"


class MCPCredentialTemplate(models.Model):
    """Credential templates required for an MCP"""

    mcp = models.ForeignKey(MCP, on_delete=models.CASCADE, related_name="credential_templates")
    name = models.CharField(max_length=255, help_text="Credential key (e.g., BASE_URL)")
    label = models.CharField(max_length=255, help_text="Display label")
    placeholder = models.CharField(max_length=255, blank=True)
    is_confidential = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("mcp", "name")
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.mcp} - {self.label}"
