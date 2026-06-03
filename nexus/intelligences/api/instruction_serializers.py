from rest_framework import serializers


class GroupedInstructionItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    instruction = serializers.CharField()


class InstructionCategoryItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    name = serializers.CharField()
    instructions = GroupedInstructionItemSerializer(many=True, required=False, default=list)


class ProjectInstructionsResponseSerializer(serializers.Serializer):
    categories = InstructionCategoryItemSerializer(many=True)
    uncategorized_instructions = GroupedInstructionItemSerializer(many=True, required=False)


class ProjectInstructionsUpdateSerializer(serializers.Serializer):
    categories = InstructionCategoryItemSerializer(many=True)
