from typing import List, Dict

from django.conf import settings

from rest_framework import serializers
from nexus.logs.models import MessageLog, RecentActivities, Message

from nexus.usecases.actions.retrieve import FlowDoesNotExist

from router.classifiers.groundedness import Groundedness
from router.repositories.orm import FlowsORMRepository
from router.classifiers import Classifier


class TagPercentageSerializer(serializers.Serializer):

    class Meta:
        model = MessageLog
        fields = [
            "action_percentage",
            "succeed_percentage",
            "failed_percentage",
        ]

    action_percentage = serializers.FloatField()
    succeed_percentage = serializers.FloatField()
    failed_percentage = serializers.FloatField()


class ContactMessageDTOSerializer(serializers.Serializer):
    contact_urn = serializers.CharField()
    text = serializers.CharField()
    llm_respose = serializers.CharField()
    content_base_uuid = serializers.CharField()
    project_uuid = serializers.CharField()


class MessageHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageLog
        fields = [
            "id",
            "created_at",
            "message_text",
            "tag",
            "classification"
        ]

    message_text = serializers.SerializerMethodField()
    tag = serializers.SerializerMethodField()

    def get_message_text(self, obj: MessageLog) -> str:
        return obj.message.text

    def get_tag(self, obj: MessageLog) -> str:
        return obj.reflection_data.get("tag", "failed")


class MessageLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageLog
        fields = [
            "id",
            "message_text",
            "message_exception",
            "contact_urn",
            "classification",
            "llm_model",
            "llm_response",
            "created_at",
        ]

    message_text = serializers.SerializerMethodField()
    message_exception = serializers.SerializerMethodField()
    contact_urn = serializers.SerializerMethodField()

    def get_message_text(self, obj: MessageLog) -> str:
        return obj.message.text

    def get_message_exception(self, obj: MessageLog) -> str:
        return obj.message.exception

    def get_contact_urn(self, obj: MessageLog) -> str:
        return obj.message.contact_urn


class MessageFullLogSerializer(MessageLogSerializer):
    class Meta:
        model = MessageLog
        fields = [
            "message_text",
            "message_exception",
            "contact_urn",
            "chunks",
            "prompt",
            "project",
            "content_base",
            "classification",
            "llm_model",
            "llm_response",
            "created_at",
            "metadata",
        ]

    def get_project(self, obj: MessageLog) -> str:
        return f"{obj.project.uuid} - {obj.project.name}"


class RecentActivitiesSerializer(serializers.ModelSerializer):

    class Meta:
        model = RecentActivities
        fields = [
            "uuid",
            "model_group",
            "action_model",
            "created_at",
            "action_details",
            "action_type",
            "project",
            "created_by",
        ]

    created_by = serializers.SerializerMethodField()
    model_group = serializers.SerializerMethodField()

    def get_created_by(self, obj: RecentActivities) -> str:
        return obj.created_by.email

    def get_model_group(self, obj: RecentActivities) -> str:

        ACTION_MODEL_GROUPS = {
            "Flow": "Action",
            "ContentBaseAgent": "Customization",
            "ContentBaseInstruction": "Customization",
            "ContentBase": "Content",
            "ContentBaseFile": "Content",
            "ContentBaseLink": "Content",
            "ContentBaseText": "Content",
            "LLM": "Config",
        }
        return ACTION_MODEL_GROUPS.get(obj.action_model, "")


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
            "contact_urn",
            "actions_started",
            "actions_type",
            "actions_uuid",
        ]

    llm_response = serializers.SerializerMethodField()
    is_approved = serializers.SerializerMethodField()
    groundedness = serializers.SerializerMethodField()
    actions_started = serializers.SerializerMethodField()
    actions_type = serializers.SerializerMethodField()
    actions_uuid = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    def get_llm_response(self, obj):
        return obj.messagelog.llm_response

    def get_is_approved(self, obj):
        return obj.messagelog.is_approved

    def get_groundedness(self, obj):
        if obj.messagelog.chunks_json:
            groundedness = Groundedness(
                llm_response=obj.messagelog.llm_response,
                llm_chunk_used=obj.messagelog.chunks,
                log=obj.messagelog
            )
            reflection_data = obj.messagelog.reflection_data

            if reflection_data and "sentence_rankings" in reflection_data:
                sentences = groundedness.extract_score_and_sentences(reflection_data.get("sentence_rankings"))
                groundedness_details: List[Dict[str, str]] = []
                for sentence in sentences:
                    sentence_stats = {
                        "sentence": sentence.get("sentence"),
                        "sources": [],
                        "score": sentence.get("score"),
                    }
                    for chunk in obj.messagelog.chunks_json:
                        evidence: str = sentence.get("evidence", "").strip('"')
                        if evidence.lower() in chunk.get("full_page").lower():
                            sentence_stats["sources"].append(
                                {
                                    "filename": chunk.get("filename"),
                                    "file_uuid": chunk.get("file_uuid")
                                }
                            )
                    groundedness_details.append(sentence_stats)
                return groundedness_details
            return
        return

    def get_actions_started(self, obj):
        if obj.messagelog.reflection_data:
            tag: str | None = obj.messagelog.reflection_data.get("tag")
            return tag == "action_started"
        return obj.messagelog.classification != Classifier.CLASSIFICATION_OTHER

    def get_actions_type(self, obj):

        if obj.messagelog.reflection_data:
            action_name: str | None = obj.messagelog.reflection_data.get("action_name")
            if action_name:
                return action_name

        return obj.messagelog.classification

    def get_actions_uuid(self, obj):
        if self.get_actions_started(obj) and obj.messagelog.reflection_data:
            action_uuid: str | None = obj.messagelog.reflection_data.get("action_uuid")

            # old logs without action info in reflection_data
            if not action_uuid:
                try:
                    action = FlowsORMRepository(
                        project_uuid=str(obj.messagelog.project.uuid)
                    ).get_project_flow_by_name(obj.messagelog.classification)
                    return str(action.pk)
                except FlowDoesNotExist:
                    return None

            return action_uuid

    def get_status(self, obj):
        status = {
            True: "S",
            False: "F"
        }
        groundedness_score: int = obj.messagelog.groundedness_score

        if groundedness_score or isinstance(groundedness_score, int):
            details: List[str] | None = self.get_groundedness(obj)
            sources_count = 0

            if details:
                for detail in details:
                    detail_score = int(detail.get("score", 0))
                    detail_source: List[str] = detail.get("sources")
                    if detail_score >= settings.GROUNDEDNESS_SCORE_AVG_THRESHOLD and detail_source:
                        sources_count += 1
                score: bool = sources_count / len(details) >= settings.GROUNDEDNESS_SOURCES_THRESHOLD / 10
                return status.get(score)
        return "F"
