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


class SupervisorAgent(models.Model):
    created_on = models.DateTimeField(auto_now_add=True)
    default = models.BooleanField(default=False, help_text="If True, this is the default supervisor for all projects")
    public = models.BooleanField(
        default=True, help_text="If True, this supervisor is public and will be available to all projects"
    )
    name = models.CharField(max_length=255)

    base_prompt = models.TextField(null=True, blank=True)

    foundation_model = models.CharField(max_length=255)
    model_vendor = models.CharField(max_length=255)
    model_has_reasoning = models.BooleanField(default=False)

    api_key = models.CharField(max_length=255, null=True, blank=True)
    api_base = models.CharField(max_length=255, null=True, blank=True)
    api_version = models.CharField(max_length=255, null=True, blank=True)

    max_tokens = models.PositiveIntegerField(default=2048)
    collaborator_max_tokens = models.PositiveIntegerField(default=2048)
    reasoning_effort = models.CharField(max_length=50, blank=True, null=True)
    reasoning_summary = models.CharField(max_length=50, blank=True, null=True, default="auto")
    tools = models.JSONField(null=True, blank=True)
    knowledge_bases = models.JSONField(null=True, blank=True)

    # human support
    human_support_prompt = models.TextField(null=True, blank=True)
    human_support_tools = models.JSONField(null=True, blank=True)

    # audio orchestration
    audio_orchestration_max_tokens = models.PositiveIntegerField(default=2048)
    audio_orchestration_collaborator_max_tokens = models.PositiveIntegerField(default=2048)

    # components
    header_components_prompt = models.TextField(null=True, blank=True)
    footer_components_prompt = models.TextField(null=True, blank=True)
    component_tools_descriptions = models.JSONField(default=dict, null=True, blank=True)
    formatter_agent_prompt = models.TextField(null=True, blank=True)
    formatter_agent_reasoning_effort = models.CharField(max_length=50, blank=True, null=True)
    formatter_agent_reasoning_summary = models.CharField(max_length=50, blank=True, null=True, default="auto")
    formatter_agent_send_only_assistant_message = models.BooleanField(default=False)
    formatter_agent_tools_descriptions = models.JSONField(default=dict, null=True, blank=True)
    formatter_agent_foundation_model = models.CharField(max_length=255)
    formatter_agent_model_has_reasoning = models.BooleanField(default=False)
    formatter_tools_descriptions = models.JSONField(default=dict, null=True, blank=True)

    # collaboratos
    collaborators_foundation_model = models.CharField(max_length=255)
    override_collaborators_foundation_model = models.BooleanField(default=False)
    default_instructions_for_collaborators = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name
