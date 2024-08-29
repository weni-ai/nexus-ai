from django.db import models
from django.db.models import Q

from uuid import uuid4

from nexus.intelligences.models import ContentBase


class TemplateAction(models.Model):

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    action_type = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    prompt = models.TextField(blank=True, null=True)
    group = models.CharField(max_length=255, null=True, blank=True)


class Flow(models.Model):
    ACTION_TYPE_CHOICES = [
        ('custom', 'Custom'),
        ('whatsapp_cart', 'WhatsApp Cart'),
        ('localization', 'Localization'),
        ('attachment', 'Attachment'),
    ]

    uuid = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=255)
    prompt = models.TextField(blank=True, null=True)
    fallback = models.BooleanField(default=False)
    content_base = models.ForeignKey(ContentBase, on_delete=models.CASCADE, related_name="flows")
    action_type = models.CharField(max_length=50, choices=ACTION_TYPE_CHOICES, default='custom')
    action_template = models.OneToOneField(TemplateAction, on_delete=models.CASCADE, related_name="flows", null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['action_type'],
                condition=~Q(action_type='custom'),
                name='unique_action_type_except_custom'
            )
        ]
