from django.db import models

from enum import Enum

from nexus.db.models import BaseModel, SoftDeleteModel
from nexus.orgs.models import Org
from nexus.users.models import User
from nexus.actions.models import Flow


class TemplateType(models.Model):
    uuid = models.UUIDField(null=True, blank=True)
    name = models.CharField(max_length=255)
    setup = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f'{self.uuid} - {self.name}'


class FeatureVersion(models.Model):
    uuid = models.UUIDField(primary_key=True, editable=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    setup = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f'{self.uuid}'


class Project(BaseModel, SoftDeleteModel):
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

    def __str__(self):
        return f'{self.uuid} - Project: {self.name} - Org: {self.org.name}'


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


class IntegratedFeatureVersion(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    feature_version = models.ForeignKey(FeatureVersion, on_delete=models.CASCADE)
    actions = models.ManyToManyField(Flow)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Project: {self.project} - Feature Version: {self.feature_version.uuid}"
