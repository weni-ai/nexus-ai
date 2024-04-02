from django.db import models

from nexus.db.models import BaseModel, SoftDeleteModel
from nexus.orgs.models import Org


class TemplateType(models.Model):
    uuid = models.UUIDField(null=True, blank=True)
    name = models.CharField(max_length=255)
    setup = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f'{self.uuid} - {self.name}'


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
