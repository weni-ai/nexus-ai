from uuid import uuid4

from django.db import models

from nexus.users.models import User


class BaseModel(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_%(class)ss")
    created_at = models.DateTimeField(auto_now_add=True)
    modified_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="modified_%(class)ss",
    )
    modified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
