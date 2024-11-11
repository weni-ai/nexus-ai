from typing import List, Dict

from rest_framework import serializers

from nexus.projects.models import Project
from nexus.logs.models import Message

from router.classifiers.groundedness import Groundedness


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['uuid', 'name', 'brain_on']
        read_only_fields = ['uuid', 'name']


class MessageDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = [
            "uuid",
            "text",
            "status",
            "llm_response",
            "is_approved",
            "groundedness",
        ]

    llm_response = serializers.SerializerMethodField()
    is_approved = serializers.SerializerMethodField()
    groundedness = serializers.SerializerMethodField()

    def get_llm_response(self, obj):
        return obj.messagelog.llm_response

    def get_is_approved(self, obj):  # TODO: ADD is_approved
        try:
            return obj.messagelog.is_approved
        except AttributeError:
            return None

    def get_groundedness(self, obj):

        groundedness = Groundedness(
            llm_response=obj.messagelog.llm_response,
            llm_chunk_used=obj.messagelog.chunks,
            log=obj.messagelog
        )
        sentences = groundedness.extract_score_and_sentences(obj.messagelog.reflection_data.get("sentence_rankings"))
        groundedness_details: List[Dict[str, str]] = []
        for sentence in sentences:
            sentence_stats = {
                "sentence": sentence.get("sentence"),
                "sources": [],
                "score": sentence.get("score"),
            }
            for chunk in obj.messagelog.chunks_json:
                if sentence.get("evidence") in chunk.get("full_page"):
                    print("sim")
                    sentence_stats["sources"].append(
                        {
                            "filename": chunk.get("filename"),
                            "file_uuid": chunk.get("file_uuid")
                        }
                    )
            groundedness_details.append(sentence_stats)
        return groundedness_details
