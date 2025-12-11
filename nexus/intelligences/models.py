from enum import Enum
from typing import Optional
from uuid import uuid4

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models

from nexus.db.models import BaseModel, SoftDeleteModel
from nexus.orgs.models import Org
from nexus.projects.models import Project


class Intelligence(BaseModel, SoftDeleteModel):
    name = models.CharField(max_length=255)
    content_bases_count = models.PositiveBigIntegerField(default=0)
    description = models.TextField(null=True, blank=True)
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="intelligences")
    is_router = models.BooleanField(default=False)

    def increase_content_bases_count(self):
        self.content_bases_count += 1
        self.save(update_fields=["content_bases_count"])

    def decrease_content_bases_count(self):
        if self.content_bases_count > 0:
            self.content_bases_count -= 1
            self.save(update_fields=["content_bases_count"])


class IntegratedIntelligence(BaseModel):
    intelligence = models.ForeignKey(Intelligence, on_delete=models.CASCADE)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE)

    def unique_router(self):
        if self.intelligence.is_router:
            existing_router = IntegratedIntelligence.objects.filter(
                project=self.project, intelligence__is_router=True
            ).exclude(uuid=self.uuid)
            if existing_router.exists():
                raise ValidationError("A project can only have one IntegratedIntelligence with is_router=True")

    def save(self, *args, **kwargs):
        self.unique_router()
        super().save(*args, **kwargs)


class Languages(Enum):
    PORTUGUESE = "pt-br"
    ENGLISH = "en-us"
    SPANISH = "es"


class ContentBase(BaseModel, SoftDeleteModel):
    LANGUAGES = (
        (Languages.ENGLISH.value, "English"),
        (Languages.PORTUGUESE.value, "Portuguese"),
        (Languages.SPANISH.value, "Spanish"),
    )

    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    intelligence = models.ForeignKey(
        Intelligence,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
    )
    language = models.CharField(max_length=10, default=Languages.PORTUGUESE.value, choices=LANGUAGES)
    is_router = models.BooleanField(default=False)


class ContentBaseFile(BaseModel, SoftDeleteModel):
    file = models.URLField(null=True, blank=True)
    file_name = models.CharField(max_length=255, null=True, blank=True)
    extension_file = models.CharField(max_length=10)
    content_base = models.ForeignKey(ContentBase, related_name="contentbasefiles", on_delete=models.CASCADE)

    @property
    def created_file_name(self):
        file_name_without_extension = self.file_name.split(".")[0]
        file_name_without_uuid = file_name_without_extension[:-37]
        return file_name_without_uuid


class ContentBaseLink(BaseModel, SoftDeleteModel):
    link = models.URLField()
    content_base = models.ForeignKey(ContentBase, related_name="contentbaselinks", on_delete=models.CASCADE)
    name = models.CharField(
        null=True, max_length=255, help_text="used to manage file with content from the link in bedrock"
    )


class ContentBaseText(BaseModel, SoftDeleteModel):
    file = models.URLField(blank=True, null=True)
    file_name = models.CharField(max_length=255, null=True, blank=True)
    text = models.TextField()
    content_base = models.ForeignKey(ContentBase, related_name="contentbasetexts", on_delete=models.CASCADE)


class ContentBaseLogs(models.Model):
    FEEDBACK_CHOICES = [
        (0, "Resposta foi em um assunto completamente diferente do perguntado."),
        (
            1,
            "Resposta foi parcialmente correta, pois além da parte correta, trouxe informações "
            "no mesmo tema mas fora do contexto disponível.",
        ),
        (
            2,
            "Resposta foi parcialmente correta, pois além da parte correta, trouxe informações "
            "de um tema completamente diferente.",
        ),
        (
            3,
            "Respondeu que não possui a informação para fornecer a resposta, porém a informação "
            "consta no contexto disponível.",
        ),
    ]

    content_base = models.ForeignKey(ContentBase, related_name="logs", on_delete=models.SET_NULL, null=True, blank=True)
    question = models.TextField()
    language = models.CharField(max_length=10)
    texts_chunks = ArrayField(models.TextField())
    full_prompt = models.TextField()
    weni_gpt_response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    wenigpt_version = models.CharField(null=True, max_length=255)
    testing = models.BooleanField(default=False)
    user_feedback = models.CharField(max_length=100, choices=FEEDBACK_CHOICES, null=True, blank=True)
    correct_answer = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.wenigpt_version}: {self.content_base} - {self.question}"

    @property
    def answer(self):
        """Format question answer"""
        try:
            response = eval(self.weni_gpt_response)
            if isinstance(response, list):
                answer = response[0]
                return answer.split("PERGUNTA")[0]
            return self.weni_gpt_response
        except Exception:
            return self.weni_gpt_response

    def update_user_feedback(self, correct_answer: bool, feedback: Optional[int] = None) -> None:
        update_fields = ["correct_answer"]
        self.correct_answer = correct_answer
        if feedback is not None:
            self.user_feedback = feedback
            update_fields.append("user_feedback")
        self.save(update_fields=update_fields)

    @property
    def feedback(self):
        return self.get_user_feedback_display()


class UserQuestion(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    text = models.TextField()
    content_base_log = models.OneToOneField(
        ContentBaseLogs,
        on_delete=models.CASCADE,
        related_name="user_question",
    )

    def __str__(self):
        return f"UserQuestion - {self.text[:50]}"


class LLM(BaseModel, SoftDeleteModel):
    model = models.CharField(max_length=255, default="WeniGPT")
    setup = models.JSONField()
    advanced_options = models.JSONField(null=True, blank=True)
    integrated_intelligence = models.OneToOneField(IntegratedIntelligence, on_delete=models.CASCADE)

    def __str__(self):
        return f"LLM - {self.model}"


class ContentBaseAgent(models.Model):
    name = models.CharField(max_length=255, null=True)
    role = models.CharField(max_length=255, null=True)
    personality = models.CharField(max_length=255, null=True)
    goal = models.TextField()
    content_base = models.OneToOneField(ContentBase, related_name="agent", on_delete=models.CASCADE)

    def __str__(self):
        return f"ContentBaseAgent - {self.name}"


class ContentBaseInstruction(models.Model):
    instruction = models.TextField()
    content_base = models.ForeignKey(ContentBase, related_name="instructions", on_delete=models.CASCADE)

    def __str__(self):
        return f"Instruction - {self.instruction[:50]}"


class Topics(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class SubTopics(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    topic = models.ForeignKey(Topics, on_delete=models.CASCADE, related_name="subtopics")

    def __str__(self):
        return f"{self.topic.name} - {self.name}"


class Conversation(models.Model):
    RESOLUTION_CHOICES = [
        (0, "Resolved"),
        (1, "Unresolved"),
        (2, "In Progress"),
        (3, "Unclassified"),
        (4, "Has Chat Room"),
    ]

    CSAT_CHOICES = [
        (1, "Very unsatisfied"),
        (2, "Unatisfied"),
        (3, "Neutral"),
        (4, "Satisfied"),
        (5, "Very satisfied"),
    ]

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    contact_urn = models.CharField(max_length=255, null=True, blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="conversations")
    external_id = models.CharField(max_length=255, null=True, blank=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    has_chats_room = models.BooleanField(default=False)
    contact_name = models.CharField(max_length=255, null=True, blank=True)
    channel_uuid = models.UUIDField(null=True, blank=True)
    topic = models.ForeignKey(Topics, on_delete=models.CASCADE, related_name="conversations", null=True, blank=True)
    subtopic = models.ForeignKey(
        SubTopics, on_delete=models.CASCADE, related_name="conversations", null=True, blank=True
    )
    nps = models.IntegerField(null=True, blank=True)
    csat = models.CharField(max_length=255, choices=CSAT_CHOICES, null=True, blank=True)
    resolution = models.CharField(max_length=255, choices=RESOLUTION_CHOICES, default=2)

    class Meta:
        indexes = [
            models.Index(fields=["project", "contact_urn", "start_date", "end_date", "channel_uuid"]),
        ]

    def __str__(self):
        return f"Conversation - {self.uuid} - {self.contact_name}"

    def get_topic(self):
        return self.topic.name if self.topic else None

    @property
    def to_json(self):
        return {
            "uuid": str(self.uuid),
            "created_at": self.created_at,
            "csat": self.csat,
            "topic": self.get_topic(),
            "project": str(self.project.uuid),
        }
