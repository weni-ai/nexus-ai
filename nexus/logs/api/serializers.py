import json
import logging

import sentry_sdk
from rest_framework import serializers

from nexus.inline_agents.models import InlineAgentMessage
from nexus.logs.models import Message, MessageLog, RecentActivities
from nexus.usecases.actions.retrieve import FlowDoesNotExist
from router.classifiers import Classifier
from router.repositories.orm import FlowsORMRepository

logger = logging.getLogger(__name__)


def _json_like(text: str) -> bool:
    text = text.lstrip()
    return bool(text) and text[0] in "[{"


def _extract_display(parsed) -> str | None:
    def _build_display(msg: dict) -> str | None:
        header = msg.get("header")
        header_text = header.get("text") if isinstance(header, dict) else None
        footer = msg.get("footer")
        base_text = msg.get("text") or msg.get("message_text")
        parts = [p for p in [header_text, base_text, footer] if p]
        return "\n".join(parts) if parts else None

    if isinstance(parsed, list) and parsed:
        item = parsed[0]
        if isinstance(item, dict):
            msg = item.get("msg") or item
            if isinstance(msg, dict):
                return _build_display(msg)
    elif isinstance(parsed, dict):
        msg = parsed.get("msg") or parsed
        if isinstance(msg, dict):
            return _build_display(msg)
    return None


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


class MessageHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageLog
        fields = ["id", "created_at", "message_text", "tag", "classification"]

    message_text = serializers.SerializerMethodField()
    tag = serializers.SerializerMethodField()

    def get_message_text(self, obj: MessageLog) -> str:
        return obj.message.text

    def get_tag(self, obj: MessageLog) -> str:
        reflection_tag = obj.reflection_data.get("tag")

        if reflection_tag == "action_started":
            return reflection_tag

        return {"S": "success", "F": "failed"}.get(obj.message.response_status)


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

    def get_groundedness(self, obj) -> str | None:
        return obj.groundedness_details

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
                    action = FlowsORMRepository(project_uuid=str(obj.messagelog.project.uuid)).get_project_flow_by_name(
                        obj.messagelog.classification
                    )
                    return str(action.pk)
                except FlowDoesNotExist:
                    return None

            return action_uuid

    def get_status(self, obj):
        return obj.response_status


class InlineConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = InlineAgentMessage
        fields = [
            "id",
            "uuid",
            "text",
            "source_type",
            "created_at",
        ]

    text = serializers.SerializerMethodField()

    def get_text(self, obj: InlineAgentMessage) -> str:
        uuid = obj.uuid
        text = obj.text
        logger.info(
            "inline_conversation_text_received",
            extra={"uuid": str(uuid), "text_len": len(text), "text_head": text[:200]},
        )

        normalized = text.strip()
        if not _json_like(normalized):
            return text

        try:
            parsed = json.loads(normalized)
            display = _extract_display(parsed)
            if display is not None:
                return display
            if isinstance(parsed, (dict, list)):
                return normalized
            return str(parsed)
        except json.JSONDecodeError as e:
            logger.warning("inline_conversation_text_decode_error", exc_info=True)
            sentry_sdk.set_tag("inline_message_uuid", str(uuid))
            sentry_sdk.set_context("inline_message_text", {"text": text})
            sentry_sdk.capture_exception(e)
            return text
