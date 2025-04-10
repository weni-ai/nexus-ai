from enum import Enum

from django.db import models

from nexus.db.models import BaseModel, SoftDeleteModel
from nexus.orgs.models import Org
from nexus.users.models import User


class TemplateType(models.Model):
    uuid = models.UUIDField(null=True, blank=True)
    name = models.CharField(max_length=255)
    setup = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f'{self.uuid} - {self.name}'


class Project(BaseModel, SoftDeleteModel):
    SENTENX = "SENTENX"
    BEDROCK = "BEDROCK"

    INDEXER_CHOICES = (
        (SENTENX, "Sentenx"),
        (BEDROCK, "Bedrock"),
    )

    DEFAULT_BACKEND = "BedrockBackend"

    name = models.CharField(max_length=255)
    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name='projects'
    )
    template_type = models.ForeignKey(
        TemplateType,
        on_delete=models.SET_NULL,
        null=True,
        related_name='template_type',
    )
    is_template = models.BooleanField(default=False)
    brain_on = models.BooleanField(default=False)
    indexer_database = models.CharField(max_length=15, choices=INDEXER_CHOICES, default=SENTENX)
    agents_backend = models.CharField(max_length=100, default=DEFAULT_BACKEND)

    human_support = models.BooleanField(default=False)
    human_support_prompt = models.TextField(null=True, blank=True)

    def __str__(self):
        return f'{self.uuid} - Project: {self.name} - Org: {self.org.name}'

    def get_user_authorization(self, user_email):
        return self.authorizations.get(user__email=user_email)

    @property
    def is_multi_agent(self):
        try:
            self.team
            return True
        except Exception:
            return False


class ProjectAuthorizationRole(Enum):
    NOT_SETTED, VIEWER, CONTRIBUTOR, MODERATOR, SUPPORT, CHAT_USER = list(range(6))

    @classmethod
    def has_value(cls, value: int):
        return value in cls._value2member_map_


class ProjectAuth(models.Model):
    class Meta:
        unique_together = ['user', 'project']

    ROLE_CHOICES = [
        (ProjectAuthorizationRole.NOT_SETTED.value, 'not set'),
        (ProjectAuthorizationRole.VIEWER.value, 'viewer'),
        (ProjectAuthorizationRole.CONTRIBUTOR.value, 'contributor'),
        (ProjectAuthorizationRole.MODERATOR.value, 'moderator'),
        (ProjectAuthorizationRole.SUPPORT.value, 'support'),
        (ProjectAuthorizationRole.CHAT_USER.value, 'chat user'),
    ]

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='authorizations'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='project_authorizations',
    )
    role = models.PositiveIntegerField(choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.user} - {self.project} - {self.role}'


class IntegratedFeature(models.Model):

    feature_uuid = models.UUIDField()
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='integrated_features'
    )
    current_version_setup = models.JSONField(default=list)
    is_integrated = models.BooleanField(default=False)
