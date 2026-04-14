from uuid import uuid4

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


class ManagerAgent(models.Model):
    uuid = models.UUIDField(default=uuid4, editable=False)
    created_on = models.DateTimeField(auto_now_add=True)
    default = models.BooleanField(
        default=False, help_text="If True, this is the default supervisor for all newly created projects"
    )
    public = models.BooleanField(
        default=True, help_text="If True, this supervisor is public and will be available to all projects"
    )
    release_date = models.DateTimeField(
        help_text="The date and time when this supervisor will be set in older projects"
    )
    name = models.CharField(max_length=255)

    base_prompt = models.TextField(null=True, blank=True)

    foundation_model = models.CharField(max_length=255)
    model_vendor = models.CharField(max_length=255)
    model_has_reasoning = models.BooleanField(default=False)

    api_key = models.CharField(max_length=255, null=True, blank=True)
    api_base = models.CharField(max_length=255, null=True, blank=True)
    api_version = models.CharField(max_length=255, null=True, blank=True)

    max_tokens = models.PositiveIntegerField(default=2048, null=True, blank=True)
    collaborator_max_tokens = models.PositiveIntegerField(default=2048, null=True, blank=True)
    reasoning_effort = models.CharField(max_length=50, blank=True, null=True)
    reasoning_summary = models.CharField(max_length=50, blank=True, null=True, default="auto")
    parallel_tool_calls = models.BooleanField(default=False)
    tools = models.JSONField(null=True, blank=True)
    knowledge_bases = models.JSONField(null=True, blank=True)

    # human support
    human_support_prompt = models.TextField(null=True, blank=True)
    human_support_tools = models.JSONField(null=True, blank=True)

    # audio orchestration
    audio_orchestration_max_tokens = models.PositiveIntegerField(default=2048, null=True, blank=True)
    audio_orchestration_collaborator_max_tokens = models.PositiveIntegerField(default=2048, null=True, blank=True)

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

    # model specific params
    manager_extra_args = models.JSONField(null=True, blank=True)
    collaborator_extra_args = models.JSONField(default=dict, blank=True)
    append_manager_extra_args = models.BooleanField(
        default=True, help_text="If True, the manager extra args will be appended to the collaborator extra args"
    )

    def __str__(self):
        return self.name


class ModelProvider(models.Model):
    uuid = models.UUIDField(default=uuid4, editable=False)
    label = models.CharField(max_length=255)
    model_vendor = models.CharField(max_length=255)
    credentials = models.JSONField(default=dict)
    models = ArrayField(models.CharField(max_length=255))
    manager_agent = models.ForeignKey(
        ManagerAgent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.label


class ProjectModelProvider(models.Model):
    uuid = models.UUIDField(default=uuid4, editable=False)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="model_providers")
    provider = models.ForeignKey(ModelProvider, on_delete=models.CASCADE)
    credentials = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_on = models.DateTimeField(auto_now_add=True, null=True)
    updated_on = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        unique_together = ("project", "provider")

    def __str__(self):
        return f"{self.project} - {self.provider}"

    @property
    def decrypted_credentials(self):
        from nexus.agents.encryption import decrypt_value

        if not isinstance(self.credentials, list):
            return self.credentials
        result = []
        for field in self.credentials:
            entry = dict(field)
            if entry.get("value") and entry.get("type") in ("PASSWORD", "TEXTAREA"):
                entry["value"] = decrypt_value(entry["value"])
            result.append(entry)
        return result

    def encrypt_credentials(self):
        from nexus.agents.encryption import encrypt_value

        if not isinstance(self.credentials, list):
            return
        encrypted = []
        for field in self.credentials:
            entry = dict(field)
            if entry.get("value") and entry.get("type") in ("PASSWORD", "TEXTAREA"):
                entry["value"] = encrypt_value(entry["value"])
            encrypted.append(entry)
        self.credentials = encrypted

    def masked_credentials(self, provider_schema):
        """Return credentials with sensitive values masked for API responses."""
        decrypted = self.decrypted_credentials
        decrypted_map = {f["id"]: f.get("value", "") for f in decrypted if isinstance(f, dict)}

        result = []
        for schema_field in provider_schema:
            field_id = schema_field["id"]
            field_type = schema_field["type"]
            raw_value = decrypted_map.get(field_id, "")

            if field_type == "TEXTAREA":
                masked = ""
            elif field_type == "PASSWORD" and raw_value:
                masked = raw_value[:4] + "..." + raw_value[-4:] if len(raw_value) > 8 else "****"
            else:
                masked = raw_value

            result.append(
                {
                    "id": field_id,
                    "type": field_type,
                    "label": schema_field["label"],
                    "value": masked,
                }
            )
        return result
