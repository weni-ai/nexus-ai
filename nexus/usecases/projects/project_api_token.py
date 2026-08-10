from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from nexus.projects.exceptions import ProjectApiTokenNameAlreadyExists, ProjectDoesNotExist
from nexus.projects.models import Project, ProjectApiToken
from nexus.usecases.projects.get_by_uuid import get_project_by_uuid


class ProjectApiTokenUseCase:
    DEFAULT_SCOPE = "read:supervisor_conversations"
    DEFAULT_EXPIRES_DAYS = 365

    def create_token(
        self,
        *,
        project: Project | None = None,
        project_uuid: str | None = None,
        name: str | None = None,
        scope: str | None = None,
        created_by=None,
        expires_at=None,
        enabled: bool = True,
    ) -> tuple[ProjectApiToken, str]:
        project = self._resolve_project(project=project, project_uuid=project_uuid)
        token_name = (name or "").strip() or self._default_name()
        token_scope = (scope or "").strip() or self.DEFAULT_SCOPE
        token_expires_at = expires_at or (timezone.now() + timedelta(days=self.DEFAULT_EXPIRES_DAYS))

        plaintext_token, salt, token_hash = ProjectApiToken.generate_token_pair()

        try:
            with transaction.atomic():
                api_token = ProjectApiToken.objects.create(
                    project=project,
                    name=token_name,
                    salt=salt,
                    token_hash=token_hash,
                    scope=token_scope,
                    created_by=created_by,
                    expires_at=token_expires_at,
                    enabled=enabled,
                )
        except IntegrityError as exc:
            raise ProjectApiTokenNameAlreadyExists() from exc

        return api_token, plaintext_token

    def serialize_created_token(self, api_token: ProjectApiToken, plaintext_token: str) -> dict:
        return {
            "id": api_token.id,
            "name": api_token.name,
            "token": plaintext_token,
            "scope": api_token.scope,
            "enabled": api_token.enabled,
            "expires_at": api_token.expires_at,
            "created_at": api_token.created_at,
        }

    def _resolve_project(self, *, project: Project | None, project_uuid: str | None) -> Project:
        if project is not None:
            return project
        if project_uuid:
            return get_project_by_uuid(project_uuid)
        raise ProjectDoesNotExist("Project is required to create an API token")

    @staticmethod
    def _default_name() -> str:
        return f"Auto {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
