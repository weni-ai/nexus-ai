from django.db import models

from nexus.db.models import BaseModel, SoftDeleteModel


class Org(BaseModel, SoftDeleteModel):
    name = models.CharField(max_length=255)
