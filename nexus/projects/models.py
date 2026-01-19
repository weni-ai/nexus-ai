import hashlib
import secrets
from enum import Enum

from django.db import models
from django.utils import timezone

from nexus.db.models import BaseModel, SoftDeleteModel
from nexus.orgs.models import Org
from nexus.users.models import User


class TemplateType(models.Model):
    uuid = models.UUIDField(null=True, blank=True)
    name = models.CharField(max_length=255)
    setup = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f"{self.uuid} - {self.name}"


class Project(BaseModel, SoftDeleteModel):
    SENTENX = "SENTENX"
    BEDROCK = "BEDROCK"

    INDEXER_CHOICES = (
        (SENTENX, "Sentenx"),
        (BEDROCK, "Bedrock"),
    )

    DEFAULT_BACKEND = "OpenAIBackend"

    name = models.CharField(max_length=255)
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="projects")
    template_type = models.ForeignKey(
        TemplateType,
        on_delete=models.SET_NULL,
        null=True,
        related_name="template_type",
    )
    is_template = models.BooleanField(default=False)
    brain_on = models.BooleanField(default=False)
    indexer_database = models.CharField(max_length=15, choices=INDEXER_CHOICES, default=SENTENX)
    agents_backend = models.CharField(max_length=100, default=DEFAULT_BACKEND)

    human_support = models.BooleanField(default=False)
    human_support_prompt = models.TextField(null=True, blank=True)
    rationale_switch = models.BooleanField(default=False)
    inline_agent_switch = models.BooleanField(default=False)
    use_components = models.BooleanField(default=False)
    default_supervisor_foundation_model = models.CharField(max_length=100, blank=True, null=True)
    default_collaborators_foundation_model = models.CharField(max_length=100, blank=True, null=True)
    use_prompt_creation_configurations = models.BooleanField(default=True)
    conversation_turns_to_include = models.IntegerField(default=10)
    exclude_previous_thinking_steps = models.BooleanField(default=True)
    guardrail = models.ForeignKey(
        "inline_agents.Guardrail",
        on_delete=models.SET_NULL,
        null=True,
        related_name="project",
        blank=True,
    )

    default_formatter_foundation_model = models.CharField(max_length=100, blank=True, null=True)
    formatter_instructions = models.TextField(null=True, blank=True)
    formatter_reasoning_effort = models.CharField(max_length=50, blank=True, null=True)
    formatter_reasoning_summary = models.CharField(max_length=50, blank=True, null=True, default="auto")
    formatter_send_only_assistant_message = models.BooleanField(default=False)
    formatter_tools_descriptions = models.JSONField(default=dict, null=True, blank=True)
    audio_orchestration_welcome_message = models.TextField(null=True, blank=True)
    supervisor_agent = models.ForeignKey(
        "inline_agents.SupervisorAgent", on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return f"{self.uuid} - Project: {self.name} - Org: {self.org.name}"

    def get_user_authorization(self, user_email):
        return self.authorizations.get(user__email=user_email)

    @property
    def is_multi_agent(self):
        try:
            _ = self.team
            return True
        except Exception:
            return False

    @property
    def formatter_agent_configurations(self) -> dict[str, str]:
        return {
            "formatter_foundation_model": self.default_formatter_foundation_model,
            "formatter_instructions": self.formatter_instructions,
            "formatter_reasoning_effort": self.formatter_reasoning_effort,
            "formatter_reasoning_summary": self.formatter_reasoning_summary,
            "formatter_send_only_assistant_message": self.formatter_send_only_assistant_message,
            "formatter_tools_descriptions": self.formatter_tools_descriptions,
        }


class ProjectAuthorizationRole(Enum):
    NOT_SETTED, VIEWER, CONTRIBUTOR, MODERATOR, SUPPORT, CHAT_USER = list(range(6))

    @classmethod
    def has_value(cls, value: int):
        return value in cls._value2member_map_


class ProjectAuth(models.Model):
    ROLE_CHOICES = [
        (ProjectAuthorizationRole.NOT_SETTED.value, "not set"),
        (ProjectAuthorizationRole.VIEWER.value, "viewer"),
        (ProjectAuthorizationRole.CONTRIBUTOR.value, "contributor"),
        (ProjectAuthorizationRole.MODERATOR.value, "moderator"),
        (ProjectAuthorizationRole.SUPPORT.value, "support"),
        (ProjectAuthorizationRole.CHAT_USER.value, "chat user"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="authorizations")
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="project_authorizations",
    )
    role = models.PositiveIntegerField(choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ["user", "project"]

    def __str__(self):
        return f"{self.user} - {self.project} - {self.role}"


class IntegratedFeature(models.Model):
    feature_uuid = models.UUIDField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="integrated_features")
    current_version_setup = models.JSONField(default=list)
    is_integrated = models.BooleanField(default=False)

    def __str__(self):
        return f"IntegratedFeature - {self.project} - {self.feature_uuid}"


class ProjectApiToken(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(max_length=255)
    token_hash = models.CharField(max_length=128)
    salt = models.CharField(max_length=64)
    scope = models.CharField(max_length=64, default="read:supervisor_conversations")
    enabled = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("project", "name")

    def __str__(self):
        return f"{self.project} - {self.name} - {self.scope}"

    @staticmethod
    def hash_token(token: str, salt: str) -> str:
        return hashlib.sha256(f"{salt}{token}".encode()).hexdigest()

    def matches(self, token: str) -> bool:
        if not self.enabled:
            return False
        if self.expires_at and self.expires_at <= timezone.now():
            return False
        return self.token_hash == self.hash_token(token, self.salt)

    @staticmethod
    def generate_token_pair() -> tuple[str, str, str]:
        token = secrets.token_urlsafe(48)
        salt = secrets.token_hex(16)
        token_hash = ProjectApiToken.hash_token(token, salt)
        return token, salt, token_hash
