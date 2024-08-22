from django.db import models
from django.db.models import Q

from nexus.intelligences.models import ContentBase


class Flow(models.Model):
    ACTION_TYPE_CHOICES = [
        ('custom', 'Custom'),
        ('whatsapp_cart', 'WhatsApp Cart'),
        ('exchanges', 'Exchanges'),
        ('offenses', 'Offenses'),
        ('greetings', 'Greetings'),
    ]

    uuid = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=255)
    prompt = models.TextField(blank=True, null=True)
    fallback = models.BooleanField(default=False)
    content_base = models.ForeignKey(ContentBase, on_delete=models.CASCADE, related_name="flows")
    action_type = models.CharField(max_length=50, choices=ACTION_TYPE_CHOICES, default='custom')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['action_type'],
                condition=~Q(action_type='custom'),
                name='unique_action_type_except_custom'
            )
        ]
