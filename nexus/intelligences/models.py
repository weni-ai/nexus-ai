from django.db import models

from nexus.db.models import BaseModel, SoftDeleteModel
from nexus.orgs.models import Org


class Intelligence(BaseModel, SoftDeleteModel):
    name = models.CharField(max_length=255)
    content_bases_count = models.PositiveBigIntegerField(default=0)
    description = models.TextField(null=True, blank=True)
    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name='intelligences'
    )


class IntegratedIntelligence(BaseModel):
    intelligence = models.ForeignKey(Intelligence, on_delete=models.CASCADE)
    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE)


class ContentBase(BaseModel, SoftDeleteModel):
    title = models.CharField(max_length=255)
    intelligence = models.ForeignKey(
        Intelligence,
        on_delete=models.CASCADE,
        related_name='%(class)ss',
    )


class ContentBaseFile(BaseModel, SoftDeleteModel):
    file = models.URLField(null=True, blank=True)
    file_name = models.CharField(max_length=255, null=True, blank=True)
    extension_file = models.CharField(max_length=10)
    content_base = models.ForeignKey(
        ContentBase, related_name='contentbasefiles', on_delete=models.CASCADE
    )


class ContentBaseLink(BaseModel, SoftDeleteModel):
    link = models.URLField()
    content_base = models.ForeignKey(
        ContentBase, related_name='contentbaselinks', on_delete=models.CASCADE
    )


class ContentBaseText(BaseModel, SoftDeleteModel):
    file = models.URLField()
    file_name = models.CharField(max_length=255)
    text = models.TextField()
    content_base = models.ForeignKey(
        ContentBase, related_name='contentbasetexts', on_delete=models.CASCADE
    )
