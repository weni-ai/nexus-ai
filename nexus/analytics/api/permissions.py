"""Auth for inline agent latency analytics (internal staff / service tools)."""

from django.conf import settings
from rest_framework import permissions


class InlineAgentLatencyAPIPermission(permissions.BasePermission):
    """Allow requests with a fixed service token or Weni Keycloak internal users."""

    def has_permission(self, request, view) -> bool:
        expected_token = getattr(settings, "INLINE_AGENT_LATENCY_API_TOKEN", "")
        if expected_token:
            authorization = request.headers.get("Authorization", "")
            if authorization == f"Bearer {expected_token}":
                return True

        try:
            from weni_commons.auth import CanCommunicateInternally, WeniAuthContext
        except ImportError:
            return False

        auth = getattr(request, "auth", None)
        if isinstance(auth, WeniAuthContext) and auth.token_type == "keycloak":
            return CanCommunicateInternally().has_permission(request, view)

        return False
