from typing import Any

from django.forms.models import model_to_dict

from nexus.events import event_manager, notify_async
from nexus.intelligences.models import ContentBase, ContentBaseInstruction, InstructionCategory


class ProjectInstructionsUseCase:
    def get_grouped_instructions(self, content_base: ContentBase) -> dict[str, list[dict[str, Any]]]:
        categories = []
        for category in content_base.instruction_categories.prefetch_related("instructions").order_by("id"):
            categories.append(
                {
                    "id": category.id,
                    "name": category.name,
                    "instructions": [
                        {"id": instruction.id, "instruction": instruction.instruction}
                        for instruction in category.instructions.all()
                    ],
                }
            )

        uncategorized = content_base.instructions.filter(category__isnull=True).order_by("id")
        uncategorized_instructions = [
            {"id": instruction.id, "instruction": instruction.instruction} for instruction in uncategorized
        ]

        payload: dict[str, list] = {"categories": categories}
        if uncategorized_instructions:
            payload["uncategorized_instructions"] = uncategorized_instructions

        return payload

    def sync_grouped_instructions(
        self,
        content_base: ContentBase,
        categories_data: list[dict[str, Any]],
        user,
        project_uuid: str,
    ) -> dict[str, list[dict[str, Any]]]:
        payload_category_ids: set[int] = set()

        for category_data in categories_data:
            category = self._upsert_category(content_base, category_data)
            payload_category_ids.add(category.id)
            self._sync_category_instructions(content_base, category, category_data.get("instructions", []), user)

        self._delete_categories_not_in_payload(content_base, payload_category_ids)

        notify_async(
            event="cache_invalidation:content_base_instruction",
            project_uuid=project_uuid,
        )

        return self.get_grouped_instructions(content_base)

    def delete_category(self, content_base: ContentBase, category_id: int, project_uuid: str) -> dict[str, list]:
        category = content_base.instruction_categories.get(id=category_id)
        self._uncategorize_instructions_for_category(category)
        category.delete()

        notify_async(
            event="cache_invalidation:content_base_instruction",
            project_uuid=project_uuid,
        )

        return self.get_grouped_instructions(content_base)

    def _delete_categories_not_in_payload(self, content_base: ContentBase, payload_category_ids: set[int]) -> None:
        categories_to_remove = content_base.instruction_categories.exclude(id__in=payload_category_ids)
        for category in categories_to_remove:
            self._uncategorize_instructions_for_category(category)
        categories_to_remove.delete()

    def _uncategorize_instructions_for_category(self, category: InstructionCategory) -> None:
        ContentBaseInstruction.objects.filter(category=category).update(category=None, suggested_category="")

    def _upsert_category(self, content_base: ContentBase, category_data: dict[str, Any]) -> InstructionCategory:
        name = (category_data.get("name") or "").strip()
        if not name:
            raise ValueError("Category name is required")

        category_id = category_data.get("id")
        if category_id:
            category = content_base.instruction_categories.get(id=category_id)
            if category.name != name:
                category.name = name
                category.save(update_fields=["name"])
            return category

        category, _ = InstructionCategory.objects.get_or_create(content_base=content_base, name=name)
        return category

    def _sync_category_instructions(
        self,
        content_base: ContentBase,
        category: InstructionCategory,
        instructions_data: list[dict[str, Any]],
        user,
    ) -> None:
        payload_instruction_ids: set[int] = set()

        for instruction_data in instructions_data:
            instruction_text = (instruction_data.get("instruction") or "").strip()
            if not instruction_text:
                continue

            instruction_id = instruction_data.get("id")
            if instruction_id:
                instruction = content_base.instructions.get(id=instruction_id)
                old_instruction_data = model_to_dict(instruction)

                instruction.instruction = instruction_text
                instruction.category = category
                instruction.suggested_category = category.name
                instruction.save(update_fields=["instruction", "category", "suggested_category"])
                instruction.refresh_from_db()

                payload_instruction_ids.add(instruction.id)
                event_manager.notify(
                    event="contentbase_instruction_activity",
                    content_base_instruction=instruction,
                    action_type="U",
                    old_instruction_data=old_instruction_data,
                    new_instruction_data=model_to_dict(instruction),
                    user=user,
                )
                continue

            created_instruction = ContentBaseInstruction.objects.create(
                content_base=content_base,
                instruction=instruction_text,
                category=category,
                suggested_category=category.name,
            )
            payload_instruction_ids.add(created_instruction.id)
            event_manager.notify(
                event="contentbase_instruction_activity",
                content_base_instruction=created_instruction,
                action_type="C",
                action_details={"old": "", "new": instruction_text},
                user=user,
            )

        category.instructions.exclude(id__in=payload_instruction_ids).delete()
