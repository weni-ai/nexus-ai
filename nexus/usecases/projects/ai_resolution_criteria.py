from django.utils import timezone

from nexus.projects.ai_resolution_criteria_constants import (
    CRITERION_TYPE_BASE,
    CRITERION_TYPE_CUSTOM,
    get_base_criteria_config,
    get_base_criterion_ids,
    serialize_base_criterion,
    serialize_custom_criterion,
)
from nexus.projects.exceptions import (
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
        mode = "update" if criterion_id else "create"

        if criterion_id:
            self._ensure_not_base_criterion(criterion_id)
            if not self._active_custom_queryset(project).filter(uuid=criterion_id).exists():
                raise ResolutionCriterionNotFound()

        existing_criteria = self._build_existing_criteria(project, exclude_criterion_id=criterion_id)
        lambda_usecase = LambdaUseCase()
        is_valid, code, message = lambda_usecase.validate_resolution_criterion(
            project_id=str(project.uuid),
            candidate_text=normalized_text,
            existing_criteria=existing_criteria,
            mode=mode,
            criterion_id=str(criterion_id) if criterion_id else None,
        )

        if not is_valid:
            raise ResolutionCriterionValidationError(code=code, message=message)

        return {"validation": {"status": True, "message": message or "Criterion validated successfully"}}

    def create_criterion(self, project_uuid: str, text: str, user) -> dict:
        project = self.get_project(project_uuid)
        normalized_text = self._normalize_text(text)

        criterion = ProjectAIResolutionCriterion.objects.create(
            project=project,
            text=normalized_text,
            created_by=user,
        )
        return serialize_custom_criterion(criterion)

    def update_criterion(self, project_uuid: str, criterion_id: str, text: str, user) -> dict:
        self._ensure_not_base_criterion(criterion_id)
        project = self.get_project(project_uuid)
        normalized_text = self._normalize_text(text)

        try:
            criterion = self._active_custom_queryset(project).get(uuid=criterion_id)
        except ProjectAIResolutionCriterion.DoesNotExist as exc:
            raise ResolutionCriterionNotFound() from exc

        criterion.text = normalized_text
        criterion.modified_by = user
        criterion.modified_at = timezone.now()
        criterion.save(update_fields=["text", "modified_by", "modified_at"])
        return serialize_custom_criterion(criterion)

    def delete_criterion(self, project_uuid: str, criterion_id: str) -> None:
        self._ensure_not_base_criterion(criterion_id)
        project = self.get_project(project_uuid)

        try:
            criterion = self._active_custom_queryset(project).get(uuid=criterion_id)
        except ProjectAIResolutionCriterion.DoesNotExist as exc:
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

    def _build_existing_criteria(self, project: Project, exclude_criterion_id: str | None = None) -> list[dict]:
        existing = [
            {"id": item["id"], "text": item["text"], "type": CRITERION_TYPE_BASE} for item in get_base_criteria_config()
        ]

        custom_queryset = self._active_custom_queryset(project)
        if exclude_criterion_id:
            custom_queryset = custom_queryset.exclude(uuid=exclude_criterion_id)

        for criterion in custom_queryset:
            existing.append(
                {
                    "id": str(criterion.uuid),
                    "text": criterion.text,
                    "type": CRITERION_TYPE_CUSTOM,
                }
            )
        return existing

    def _ensure_not_base_criterion(self, criterion_id: str) -> None:
        if criterion_id in get_base_criterion_ids():
            raise UnauthorizedBaseCriterionChange()

    def _normalize_text(self, text: str) -> str:
        normalized = (text or "").strip()
        if not normalized:
            raise ValueError("Text is required")
        return normalized
