from django.db import models


class Supervisor(models.Model):
    created_on = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=255)
    instruction = models.TextField(verbose_name="Default prompt")
    foundation_model = models.CharField(max_length=255)
    prompt_override_configuration = models.JSONField()
    action_groups = models.JSONField()
    knowledge_bases = models.JSONField()

    human_support_prompt = models.TextField(null=True, blank=True)
    human_support_action_groups = models.JSONField(null=True, blank=True)

    components_prompt = models.TextField(null=True, blank=True)
    components_human_support_prompt = models.TextField(null=True, blank=True)
