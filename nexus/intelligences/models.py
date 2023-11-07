from django.db import models

from nexus.db.models import BaseModel, SoftDeleteModel
from nexus.orgs.models import Org


class Intelligence(BaseModel, SoftDeleteModel):
    name = models.CharField(max_length=255)
    content_bases_count = models.PositiveBigIntegerField(default=0)
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

    class Meta:
        abstract = True


class ContentBaseFile(ContentBase):
    file = models.FileField(upload_to='')
    extension_file = models.CharField(max_length=10)


class ContentBaseLink(ContentBase):
    link = models.URLField()


class ContentBaseText(ContentBase):
    text = models.TextField()
