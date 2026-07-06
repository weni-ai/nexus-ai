from rest_framework import serializers


class GroupedInstructionItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    instruction = serializers.CharField()


class GroupedInstructionPatchItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    instruction = serializers.CharField()


class InstructionCategoryItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    name = serializers.CharField()
    instructions = GroupedInstructionItemSerializer(many=True, required=False, default=list)


class InstructionCategoryCreateRefSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    name = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs.get("id") is not None:
            return attrs
        if (attrs.get("name") or "").strip():
            return attrs
        raise serializers.ValidationError("Category id or name is required when category is provided")


class InstructionCategoryPatchSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    name = serializers.CharField(required=False, allow_blank=True)
    instructions = GroupedInstructionPatchItemSerializer(many=True, required=False)

    def validate(self, attrs):
        if attrs.get("id") is not None:
            return attrs
        if (attrs.get("name") or "").strip():
            return attrs
        raise serializers.ValidationError("Category id or name is required")


class ProjectInstructionsResponseSerializer(serializers.Serializer):
    categories = InstructionCategoryItemSerializer(many=True)
    uncategorized_instructions = GroupedInstructionItemSerializer(many=True, required=False)


class ProjectInstructionsCreateSerializer(serializers.Serializer):
    instruction = serializers.CharField()
    category = InstructionCategoryCreateRefSerializer(required=False, allow_null=True)


class ProjectInstructionsPatchSerializer(serializers.Serializer):
    categories = InstructionCategoryPatchSerializer(many=True, required=False)
    uncategorized_instructions = GroupedInstructionPatchItemSerializer(many=True, required=False)

    def validate(self, attrs):
        if not attrs.get("categories") and not attrs.get("uncategorized_instructions"):
            raise serializers.ValidationError("At least one of categories or uncategorized_instructions is required")
        return attrs


class InstructionsExportColumnsSerializer(serializers.Serializer):
    category = serializers.CharField()
    instruction = serializers.CharField()


class InstructionsExportCategoryLabelsSerializer(serializers.Serializer):
    uncategorized = serializers.CharField()
    default = serializers.CharField()


class ProjectInstructionsExportSerializer(serializers.Serializer):
    columns = InstructionsExportColumnsSerializer(
        help_text="Localized CSV column headers sent by the frontend.",
    )
    category_labels = InstructionsExportCategoryLabelsSerializer(
        help_text="Localized labels for uncategorized and default instruction rows.",
    )
    default_instructions = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        default=list,
        help_text="Default instruction texts from the frontend to include in the CSV export.",
    )
