from rest_framework import serializers


class AIResolutionCriteriaListResponseSerializer(serializers.Serializer):
    base_criteria = serializers.ListField(child=serializers.DictField())
    custom_criteria = serializers.ListField(child=serializers.DictField())


class AIResolutionCriterionItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    text = serializers.CharField()
    type = serializers.CharField()
    editable = serializers.BooleanField()
    deletable = serializers.BooleanField()
    created_at = serializers.DateTimeField(required=False)
    updated_at = serializers.DateTimeField(required=False)


class AIResolutionCriteriaValidateRequestSerializer(serializers.Serializer):
    text = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)
    criterion_id = serializers.UUIDField(required=False, allow_null=True)


class AIResolutionCriteriaValidateResponseSerializer(serializers.Serializer):
    validation = serializers.DictField()


class AIResolutionCriteriaCreateRequestSerializer(serializers.Serializer):
    text = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)


class AIResolutionCriteriaUpdateRequestSerializer(serializers.Serializer):
    text = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)


class AIResolutionCriteriaDeleteResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
