from django.db import models

from nexus.intelligences.models import ContentBase


class Flow(models.Model):
    uuid = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=255)
    prompt = models.TextField()
    fallback = models.BooleanField(default=False)
    content_base = models.ForeignKey(ContentBase, on_delete=models.CASCADE, related_name="flows")
    action_usage = models.IntegerField(default=0)
