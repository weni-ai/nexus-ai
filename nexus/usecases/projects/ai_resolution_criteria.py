from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from nexus.projects.ai_resolution_criteria_constants import (
    MAX_CUSTOM_CRITERIA,
    get_base_criteria_config,
    get_base_criterion_ids,
    serialize_base_criterion,
    serialize_custom_criterion,
)
from nexus.projects.exceptions import (
    ResolutionCriterionLimitReached,
    ResolutionCriterionNotFound,
    ResolutionCriterionValidationError,
    UnauthorizedBaseCriterionChange,
)
from nexus.projects.models import Project, ProjectAIResolutionCriterion
from nexus.usecases.intelligences.lambda_usecase import LambdaUseCase
from nexus.usecases.projects.get_by_uuid import get_project_by_uuid


class AIResolutionCriteriaUseCase:
    def get_project(self, project_uuid: str) -> Project:
        return get_project_by_uuid(project_uuid)

    def list_criteria(self, project_uuid: str) -> dict:
        project = self.get_project(project_uuid)
        base_criteria = [serialize_base_criterion(item) for item in get_base_criteria_config()]
        custom_criteria = [
            serialize_custom_criterion(criterion)
            for criterion in self._active_custom_queryset(project).order_by("created_at")
        ]
        return {"base_criteria": base_criteria, "custom_criteria": custom_criteria}

    def validate_criterion(self, project_uuid: str, text: str, criterion_id: str | None = None) -> dict:
        project = self.get_project(project_uuid)
        normalized_text = self._normalize_text(text)

        exclude_criterion_id = None
        if criterion_id:
            exclude_criterion_id = self._parse_custom_criterion_id(criterion_id)
            if not self._active_custom_queryset(project).filter(uuid=exclude_criterion_id).exists():
                raise ResolutionCriterionNotFound()

        user_rules = self._build_user_rules_for_validation(
            project=project,
            candidate_text=normalized_text,
            exclude_criterion_id=exclude_criterion_id,
        )
        lambda_result = LambdaUseCase().validate_resolution_criterion(user_rules=user_rules)

        if not lambda_result["valid"]:
            invalid_rules = [rule for rule in lambda_result.get("rules", []) if not rule.get("valid", True)]
            message = "The criterion is invalid"
            if invalid_rules:
                candidate_invalid = next(
                    (rule for rule in invalid_rules if rule.get("rule") == normalized_text),
                    None,
                )
                message = (candidate_invalid or invalid_rules[0]).get("reason") or message
            raise ResolutionCriterionValidationError(
                code="INVALID_CRITERION",
                message=message,
                rules=lambda_result.get("rules", []),
            )

        validation = {"status": True, "message": "Criterion validated successfully"}
        if lambda_result.get("rules"):
            validation["rules"] = lambda_result["rules"]
        return {"validation": validation}

    def create_criterion(self, project_uuid: str, text: str, user) -> dict:
        project = self.get_project(project_uuid)
        normalized_text = self._normalize_text(text)

        with transaction.atomic():
            Project.objects.select_for_update().get(pk=project.pk)
            active_count = self._active_custom_queryset(project).count()
            if active_count >= MAX_CUSTOM_CRITERIA:
                raise ResolutionCriterionLimitReached()

            criterion = ProjectAIResolutionCriterion.objects.create(
                project=project,
                text=normalized_text,
                created_by=user,
            )
        return serialize_custom_criterion(criterion)

    def update_criterion(self, project_uuid: str, criterion_id: str, text: str, user) -> dict:
        parsed_criterion_id = self._parse_custom_criterion_id(criterion_id)
        project = self.get_project(project_uuid)
        normalized_text = self._normalize_text(text)

        try:
            criterion = self._active_custom_queryset(project).get(uuid=parsed_criterion_id)
        except (ProjectAIResolutionCriterion.DoesNotExist, DjangoValidationError) as exc:
            raise ResolutionCriterionNotFound() from exc

        criterion.text = normalized_text
        criterion.modified_by = user
        criterion.modified_at = timezone.now()
        criterion.save(update_fields=["text", "modified_by", "modified_at"])
        return serialize_custom_criterion(criterion)

    def delete_criterion(self, project_uuid: str, criterion_id: str) -> None:
        parsed_criterion_id = self._parse_custom_criterion_id(criterion_id)
        project = self.get_project(project_uuid)

        try:
            criterion = self._active_custom_queryset(project).get(uuid=parsed_criterion_id)
        except (ProjectAIResolutionCriterion.DoesNotExist, DjangoValidationError) as exc:
            raise ResolutionCriterionNotFound() from exc

        criterion.is_active = False
        criterion.deleted_at = timezone.now()
        criterion.save(update_fields=["is_active", "deleted_at"])

    def _active_custom_queryset(self, project: Project):
        return ProjectAIResolutionCriterion.objects.filter(
            project=project,
            is_active=True,
            deleted_at__isnull=True,
        )

    def _build_user_rules_for_validation(
        self,
        project: Project,
        candidate_text: str,
        exclude_criterion_id: UUID | None = None,
    ) -> list[str]:
        """Build full user_rules for Lambda: base + active customs + candidate.

        On update, the criterion being edited is excluded so its new text
        (candidate) replaces the stored text in the set sent to the Lambda.
        """
        user_rules = [item["text"] for item in get_base_criteria_config() if item.get("text")]
        customs = self._active_custom_queryset(project).order_by("created_at")
        if exclude_criterion_id is not None:
            customs = customs.exclude(uuid=exclude_criterion_id)
        user_rules.extend(customs.values_list("text", flat=True))
        user_rules.append(candidate_text)
        return user_rules

    def _ensure_not_base_criterion(self, criterion_id: str) -> None:
        if criterion_id in get_base_criterion_ids():
            raise UnauthorizedBaseCriterionChange()

    def _parse_custom_criterion_id(self, criterion_id: str) -> UUID:
        self._ensure_not_base_criterion(criterion_id)
        try:
            return UUID(str(criterion_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ResolutionCriterionNotFound() from exc

    def _normalize_text(self, text: str) -> str:
        normalized = (text or "").strip()
        if not normalized:
            raise ValueError("Text is required")
        return normalized
