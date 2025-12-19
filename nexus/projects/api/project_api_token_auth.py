from datetime import timedelta

from django.utils import timezone
from rest_framework import authentication, permissions
from rest_framework.exceptions import AuthenticationFailed

from nexus.projects.models import ProjectApiToken


class ProjectApiKeyAuthentication(authentication.BaseAuthentication):
    keyword = "ApiKey"

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization", "")
        if not isinstance(auth_header, str) or not auth_header.startswith(f"{self.keyword} "):
            return None

        raw_token = auth_header.split(" ", 1)[1]

        resolver_match = getattr(getattr(request, "_request", None), "resolver_match", None)
        resolver_kwargs = getattr(resolver_match, "kwargs", {}) if resolver_match else {}
        project_uuid = (
            resolver_kwargs.get("project_uuid")
            or (request.query_params.get("project_uuid") if hasattr(request, "query_params") else None)
            or request.data.get("project_uuid")
        )

        token_qs = (
            ProjectApiToken.objects.filter(project__uuid=project_uuid, enabled=True)
            if project_uuid
            else ProjectApiToken.objects.filter(enabled=True)
        )

        for token in token_qs:
            if token.matches(raw_token):
                if token.expires_at and token.expires_at <= timezone.now():
                    raise AuthenticationFailed("Expired Token")
                now = timezone.now()
                token.last_used_at = now
                token.expires_at = now + timedelta(days=365)
                token.save(update_fields=["last_used_at", "expires_at"])
                return (
                    None,
                    {"project_uuid": str(token.project.uuid), "token_id": token.id, "scope": token.scope},
                )

        raise AuthenticationFailed("Invalid token")


class ProjectApiKeyPermission(permissions.BasePermission):
    required_scope = "read:supervisor_conversations"

    def has_permission(self, request, view):
        auth = getattr(request, "auth", None)
        if not isinstance(auth, dict):
            return False
        if auth.get("scope") != self.required_scope:
            return False
        project_uuid = view.kwargs.get("project_uuid") or request.query_params.get("project_uuid")
        return project_uuid == auth.get("project_uuid")
