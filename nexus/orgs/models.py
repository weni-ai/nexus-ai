from enum import Enum

from django.db import models

from nexus.db.models import BaseModel, SoftDeleteModel


class Org(BaseModel, SoftDeleteModel):
    name = models.CharField(max_length=255)
    inteligence_organization = models.PositiveIntegerField()  # for migrating purposes 


class Role(Enum):
    NOT_SETTED, VIEWER, CONTRIBUTOR, ADMIN = list(range(4))

    @classmethod
    def has_value(cls, value: int):
        return value in cls._value2member_map_


class OrgAuth(models.Model):
    class Meta:
        unique_together = ['user', 'org']

    ROLE_CHOICES = [
        (Role.NOT_SETTED.value, 'not set'),
        (Role.VIEWER.value, 'viewer'),
        (Role.CONTRIBUTOR.value, 'contributor'),
        (Role.ADMIN.value, 'admin'),
    ]

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name='authorizations'
    )
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='authorizations_user',
    )
    role = models.PositiveIntegerField(choices=ROLE_CHOICES)
