import unicodedata
import re
import string
from typing import List, Dict
from uuid import uuid4

from django.db import models
from django.conf import settings
from django.contrib.postgres.fields import ArrayField

from nexus.users.models import User
from nexus.projects.models import Project
from nexus.intelligences.models import ContentBase, Intelligence


class TextComparer:
    @staticmethod
    def similarity(sentence_a: str, sentence_b: str) -> float:
        from difflib import SequenceMatcher
        return SequenceMatcher(None, sentence_a, sentence_b).ratio()

    @staticmethod
    def clean_string(s: str) -> str:
        s = s.lower()
        s = " ".join(s.split())
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("utf-8")
        s = re.sub(f"[{re.escape(string.punctuation)}]", "", s)
        return s

    @staticmethod
    def string_in_text(sentence: str, text: str, compare_similarity: bool = True, similarity_threshold: float = 0.8) -> bool:
        keywords: List[str] = sentence.split()

        if compare_similarity:
            keywords_in_text = []
            for keyword in keywords:
                keyword_in_text = any(TextComparer.similarity(keyword, word) >= similarity_threshold for word in text.split())
                keywords_in_text.append(keyword_in_text)
            return all(keywords_in_text)

        keywords_in_text = [keyword in text for keyword in keywords]
        return all(keywords_in_text)


class Message(models.Model):

    STATUS_CHOICES = (
        ("F", "fail"),
        ("P", "processing"),
        ("S", "success")
    )

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    text = models.TextField()
    contact_urn = models.CharField(max_length=255)
    status = models.CharField(
        max_length=1, choices=STATUS_CHOICES, default='P'
    )
    exception = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.status} - {self.contact_urn}"

    @property
    def groundedness_details(self):
        messagelog_groundedness_details = self.messagelog.groundedness_details

        if not messagelog_groundedness_details:
            from router.classifiers.groundedness import Groundedness

            if self.messagelog.chunks_json:
                groundedness = Groundedness(
                    llm_response=self.messagelog.llm_response,
                    llm_chunk_used=self.messagelog.chunks,
                    log=self.messagelog
                )
                reflection_data = self.messagelog.reflection_data

                if reflection_data and "sentence_rankings" in reflection_data:
                    sentences = groundedness.extract_score_and_sentences(reflection_data.get("sentence_rankings"))
                    groundedness_details: List[Dict[str, str]] = []
                    for sentence in sentences:
                        sentence_stats = {
                            "sentence": sentence.get("sentence"),
                            "sources": [],
                            "score": sentence.get("score"),
                        }
                        for chunk in self.messagelog.chunks_json:

                            evidence: str = sentence.get("evidence", "")
                            clean_evidence: str = TextComparer.clean_string(evidence)
                            clean_chunk: str = TextComparer.clean_string(chunk.get("full_page", ""))

                            if TextComparer.string_in_text(clean_evidence, clean_chunk):
                                sentence_stats["sources"].append(
                                    {
                                        "filename": chunk.get("filename"),
                                        "file_uuid": chunk.get("file_uuid")
                                    }
                                )
                        groundedness_details.append(sentence_stats)
                    self.messagelog.groundedness_details = groundedness_details
                    self.messagelog.save(update_fields=["groundedness_details"])
                    return groundedness_details
                return
            return
        return messagelog_groundedness_details

    @property
    def response_status(self):
        status = {
            True: "S",
            False: "F"
        }
        groundedness_score: int = self.messagelog.groundedness_score

        if groundedness_score or isinstance(groundedness_score, int):
            # details: List[str] | None = self.groundedness_details
            # sources_count = 0

            # if details:
                # for detail in details:
                #     detail_score = int(detail.get("score", 0))
                #     detail_source: List[str] = detail.get("sources")
                #     if detail_score >= settings.GROUNDEDNESS_SCORE_AVG_THRESHOLD and detail_source:
                #         sources_count += 1
                # score: bool = sources_count / len(details) >= settings.GROUNDEDNESS_SOURCES_THRESHOLD / 10
            return status.get(groundedness_score >= settings.GROUNDEDNESS_SCORE_AVG_THRESHOLD)
        return "F"


class MessageLog(models.Model):
    message = models.OneToOneField(Message, on_delete=models.CASCADE)
    chunks = ArrayField(models.TextField(), null=True)
    chunks_json = ArrayField(models.JSONField(), null=True)
    prompt = models.TextField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True)
    content_base = models.ForeignKey(
        ContentBase, on_delete=models.CASCADE, null=True
    )
    classification = models.CharField(max_length=255, null=True)
    llm_model = models.CharField(max_length=255, null=True)
    llm_response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(null=True)
    source = models.CharField(max_length=255, null=True)

    groundedness_score = models.IntegerField(null=True)
    groundedness_details = models.JSONField(null=True)
    reflection_data = models.JSONField(null=True)

    is_approved = models.BooleanField(null=True)

    def __str__(self) -> str:
        return f"{self.message}"


class RecentActivities(models.Model):

    ACTION_CHOICES = (
        ("C", "created"),
        ("U", "updated"),
        ("D", "deleted")
    )

    action_model = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    action_details = models.JSONField(null=True, blank=True)
    action_type = models.CharField(max_length=1, choices=ACTION_CHOICES)

    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    intelligence = models.ForeignKey(Intelligence, on_delete=models.CASCADE)

    def __str__(self) -> str:
        return f"{self.uuid} - {self.action_type}"
