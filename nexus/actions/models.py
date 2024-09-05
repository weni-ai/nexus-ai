from django.db import models
from django.db.models import Q
from enum import Enum

from uuid import uuid4

from nexus.intelligences.models import ContentBase


class Languages(Enum):
    PORTUGUESE = 'pt-br'
    ENGLISH = 'en-us'
    SPANISH = 'es'


class Group(Enum):
    SUPPORT = 'support'
    INTERACTIONS = 'interactions'
    SHOPPING = 'shopping'


class TemplateAction(models.Model):
    LANGUAGES = (
        (Languages.ENGLISH.value, "English"),
        (Languages.PORTUGUESE.value, "Portuguese"),
        (Languages.SPANISH.value, "Spanish")
    )

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    action_type = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    prompt = models.TextField(blank=True, null=True)
    group = models.CharField(max_length=255, null=True, blank=True)
    display_prompt = models.CharField(max_length=255, null=True, blank=True)
    language = models.CharField(
        max_length=10,
        default=Languages.PORTUGUESE.value,
        choices=LANGUAGES
    )


class Flow(models.Model):
    ACTION_TYPE_CHOICES = [
        ('custom', 'Custom'),
        ('whatsapp_cart', 'WhatsApp Cart'),
        ('localization', 'Localization'),
        ('attachment', 'Attachment'),
    ]

    group = (
        (Group.SUPPORT.value, "Support"),
        (Group.INTERACTIONS.value, "Interactions"),
        (Group.SHOPPING.value, "Shopping")
    )

    uuid = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=255)
    prompt = models.TextField(blank=True, null=True)
    fallback = models.BooleanField(default=False)
    content_base = models.ForeignKey(ContentBase, on_delete=models.CASCADE, related_name="flows")
    action_type = models.CharField(max_length=50, choices=ACTION_TYPE_CHOICES, default='custom')
    action_template = models.OneToOneField(TemplateAction, on_delete=models.CASCADE, related_name="flows", null=True)
    group = models.CharField(
        max_length=255,
        choices=group,
        default=Group.INTERACTIONS.value
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['action_type', 'action_type'],
                condition=~Q(action_type='custom'),
                name='unique_action_type_except_custom_per_content_base'
            )
        ]
