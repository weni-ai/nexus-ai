from django.contrib.postgres.fields import ArrayField
from django.db import models


class OpenAISupervisor(models.Model):
    created_on = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=255, default="OpenAI Supervisor")
    instruction = models.TextField()
    foundation_model = models.CharField(max_length=255)
    prompt_override_configuration = models.JSONField()
    action_groups = models.JSONField()
    knowledge_bases = models.JSONField()

    human_support_prompt = models.TextField(null=True, blank=True)
    human_support_action_groups = models.JSONField(null=True, blank=True)

    components_prompt = models.TextField(null=True, blank=True)
    components_human_support_prompt = models.TextField(
        null=True, blank=True, verbose_name="Formatter agent instructions"
    )  # TODO: rename attribute to formatter_agent_instructions
    components_instructions_up_prompt = models.TextField(
        null=True, blank=True, verbose_name="Components Instructions UP"
    )

    default_instructions_for_collaborators = models.TextField(
        null=True, blank=True, help_text="Instructions that will be added to every collaborator"
    )
    max_tokens = models.IntegerField(
        null=True, blank=True, help_text="Maximum number of tokens to generate", default=2048
    )
    max_tokens_collaborator = models.IntegerField(
        null=True, blank=True, help_text="Maximum number of tokens to generate", default=2048
    )
    audio_orchestration_max_tokens = models.IntegerField(
        null=True, blank=True, help_text="Maximum number of tokens to generate for audio orchestration", default=2048
    )
    audio_orchestration_max_tokens_collaborator = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of tokens to generate for audio orchestration for collaborators",
        default=2048,
    )

    exclude_tools_from_audio_orchestration = ArrayField(models.CharField(max_length=255), default=list, blank=True)
    exclude_tools_from_text_orchestration = ArrayField(models.CharField(max_length=255), default=list, blank=True)

    transcription_prompt = models.TextField(null=True, blank=True, help_text="Prompt to use for transcription")

    class Meta:
        verbose_name = "OpenAI Supervisor"
        verbose_name_plural = "OpenAI Supervisors"

    def __str__(self):
        return self.name
