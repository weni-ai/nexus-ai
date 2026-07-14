import csv
import io
from typing import Any

from django.db import IntegrityError
from django.forms.models import model_to_dict

from nexus.events import event_manager, notify_async
from nexus.intelligences.models import ContentBase, ContentBaseInstruction, InstructionCategory


class DuplicateCategoryNameError(Exception):
    """Raised when creating or renaming a category would duplicate an existing name."""


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

    def build_instructions_csv(
        self,
        content_base: ContentBase,
        *,
        category_column: str,
        instruction_column: str,
        uncategorized_label: str,
        default_label: str,
        default_instructions: list[str] | None = None,
    ) -> str:
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow([category_column, instruction_column])

        for category in content_base.instruction_categories.prefetch_related("instructions").order_by("id"):
            for instruction in category.instructions.all().order_by("id"):
                writer.writerow([category.name, instruction.instruction])

        uncategorized = content_base.instructions.filter(category__isnull=True).order_by("id")
        for instruction in uncategorized:
            writer.writerow([uncategorized_label, instruction.instruction])

        for raw_text in default_instructions or []:
            instruction_text = (raw_text or "").strip()
            if instruction_text:
                writer.writerow([default_label, instruction_text])

        return output.getvalue()

    def create_instruction(
        self,
        content_base: ContentBase,
        instruction_text: str,
        category_data: dict[str, Any] | None,
        user,
        project_uuid: str,
    ) -> dict[str, list[dict[str, Any]]]:
        instruction_text = (instruction_text or "").strip()
        if not instruction_text:
            raise ValueError("Instruction text is required")

        category = self._resolve_category_for_create(content_base, category_data)
        extra = {"category": category, "suggested_category": category.name} if category else {}
        created_instruction = ContentBaseInstruction.objects.create(
            content_base=content_base,
            instruction=instruction_text,
            **extra,
        )

        event_manager.notify(
            event="contentbase_instruction_activity",
            content_base_instruction=created_instruction,
            action_type="C",
            action_details={"old": "", "new": instruction_text},
            user=user,
        )

        notify_async(
            event="cache_invalidation:content_base_instruction",
            project_uuid=project_uuid,
        )

        return self.get_grouped_instructions(content_base)

    def patch_grouped_instructions(
        self,
        content_base: ContentBase,
        categories_data: list[dict[str, Any]] | None,
        uncategorized_data: list[dict[str, Any]] | None,
        user,
        project_uuid: str,
    ) -> dict[str, list[dict[str, Any]]]:
        if categories_data:
            for category_data in categories_data:
                category = self._resolve_category_for_patch(content_base, category_data)
                if "instructions" in category_data:
                    self._patch_category_instructions(content_base, category, category_data["instructions"], user)

        if uncategorized_data:
            self._patch_uncategorized_instructions(content_base, uncategorized_data, user)

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

    def _resolve_category_for_create(
        self, content_base: ContentBase, category_data: dict[str, Any] | None
    ) -> InstructionCategory | None:
        if not category_data:
            return None

        category_id = category_data.get("id")
        if category_id is not None:
            return content_base.instruction_categories.get(id=category_id)

        name = (category_data.get("name") or "").strip()
        if not name:
            raise ValueError("Category id or name is required when category is provided")

        return self._create_category_by_name(content_base, name)

    def _uncategorize_instructions_for_category(self, category: InstructionCategory) -> None:
        ContentBaseInstruction.objects.filter(category=category).update(category=None, suggested_category="")

    def _resolve_category_for_patch(
        self, content_base: ContentBase, category_data: dict[str, Any]
    ) -> InstructionCategory:
        category_id = category_data.get("id")
        if category_id is not None:
            category = content_base.instruction_categories.get(id=category_id)
            name = (category_data.get("name") or "").strip()
            if name and category.name != name:
                self._ensure_category_name_available(content_base, name, exclude_category_id=category.id)
                category.name = name
                try:
                    category.save(update_fields=["name"])
                except IntegrityError as error:
                    raise DuplicateCategoryNameError from error
            return category

        name = (category_data.get("name") or "").strip()
        if not name:
            raise ValueError("Category id or name is required")

        existing_category = content_base.instruction_categories.filter(name=name).first()
        if existing_category:
            return existing_category

        return self._create_category_by_name(content_base, name)

    def _ensure_category_name_available(
        self,
        content_base: ContentBase,
        name: str,
        *,
        exclude_category_id: int | None = None,
    ) -> None:
        queryset = content_base.instruction_categories.filter(name=name)
        if exclude_category_id is not None:
            queryset = queryset.exclude(id=exclude_category_id)
        if queryset.exists():
            raise DuplicateCategoryNameError

    def _create_category_by_name(self, content_base: ContentBase, name: str) -> InstructionCategory:
        self._ensure_category_name_available(content_base, name)
        try:
            return InstructionCategory.objects.create(content_base=content_base, name=name)
        except IntegrityError as error:
            raise DuplicateCategoryNameError from error

    def _patch_category_instructions(
        self,
        content_base: ContentBase,
        category: InstructionCategory,
        instructions_data: list[dict[str, Any]],
        user,
    ) -> None:
        for instruction_data in instructions_data:
            instruction_text = (instruction_data.get("instruction") or "").strip()
            if not instruction_text:
                continue

            instruction = content_base.instructions.get(id=instruction_data["id"])
            old_instruction_data = model_to_dict(instruction)

            instruction.instruction = instruction_text
            instruction.category = category
            instruction.suggested_category = category.name
            instruction.save(update_fields=["instruction", "category", "suggested_category"])
            instruction.refresh_from_db()

            event_manager.notify(
                event="contentbase_instruction_activity",
                content_base_instruction=instruction,
                action_type="U",
                old_instruction_data=old_instruction_data,
                new_instruction_data=model_to_dict(instruction),
                user=user,
            )

    def _patch_uncategorized_instructions(
        self,
        content_base: ContentBase,
        instructions_data: list[dict[str, Any]],
        user,
    ) -> None:
        for instruction_data in instructions_data:
            instruction_text = (instruction_data.get("instruction") or "").strip()
            if not instruction_text:
                continue

            instruction = content_base.instructions.get(id=instruction_data["id"], category__isnull=True)
            old_instruction_data = model_to_dict(instruction)

            instruction.instruction = instruction_text
            instruction.suggested_category = ""
            instruction.save(update_fields=["instruction", "suggested_category"])
            instruction.refresh_from_db()

            event_manager.notify(
                event="contentbase_instruction_activity",
                content_base_instruction=instruction,
                action_type="U",
                old_instruction_data=old_instruction_data,
                new_instruction_data=model_to_dict(instruction),
                user=user,
            )
