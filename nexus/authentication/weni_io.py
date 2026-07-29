"""Hybrid JWT/Keycloak auth helpers for App IO endpoints."""

from typing import Optional

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from weni_commons.auth import (
    CanCommunicateInternally,
    WeniAuthContext,
    WeniAuthentication,
    WeniAuthViewMixin,
)

from nexus.authentication.authentication import ExternalTokenAuthentication
from nexus.projects.api.permissions import ExternalTokenPermission, ProjectPermission


class ExternalTokenAuthenticationWithHeader(ExternalTokenAuthentication):
    """Preserve 401 WWW-Authenticate when this class is listed first."""

    def authenticate_header(self, request):
        return "Bearer"


WENI_IO_AUTHENTICATION_CLASSES = [ExternalTokenAuthenticationWithHeader, WeniAuthentication]


class HybridIOIdentityPermission(permissions.BasePermission):
    """Require a Weni auth context, Django user, or external superuser token.

    ExternalTokenAuthentication historically sets ``request.user`` to a bool,
    so ``IsAuthenticated`` cannot be used directly.
    """

    def has_permission(self, request: Request, view) -> bool:
        if isinstance(getattr(request, "auth", None), WeniAuthContext):
            return True

        if ExternalTokenPermission().has_permission(request, view):
            return True

        user = getattr(request, "user", None)
        return bool(getattr(user, "is_authenticated", False)) if hasattr(user, "is_authenticated") else False


class HybridIOProjectPermission(permissions.BasePermission):
    """Authorize App IO routes under hybrid JWT + Keycloak auth.

    - JWT: ``project_uuid`` claim is required (IO always sends it on these routes).
    - Keycloak: keep existing project authorization checks.
    - Legacy external/internal tokens remain allowed for compatibility.
    """

    def has_permission(self, request: Request, view) -> bool:
        auth = request.auth
        if isinstance(auth, WeniAuthContext) and auth.is_jwt:
            return auth.has_project_uuid

        if ExternalTokenPermission().has_permission(request, view):
            return True

        user = getattr(request, "user", None)
        if not hasattr(user, "is_authenticated") or not user.is_authenticated:
            return False

        if CanCommunicateInternally().has_permission(request, view):
            return True

        return ProjectPermission().has_permission(request, view)


class HybridIOInternalPermission(permissions.BasePermission):
    """Like HybridIOProjectPermission, but Keycloak stays internal-only.

    Used by commerce-router, which historically required
    ``users.can_communicate_internally`` and should not open to every
    project member via Keycloak.
    """

    def has_permission(self, request: Request, view) -> bool:
        auth = request.auth
        if isinstance(auth, WeniAuthContext) and auth.is_jwt:
            return auth.has_project_uuid

        if ExternalTokenPermission().has_permission(request, view):
            return True

        user = getattr(request, "user", None)
        if not hasattr(user, "is_authenticated") or not user.is_authenticated:
            return False

        return CanCommunicateInternally().has_permission(request, view)


class WeniIOAuthViewMixin(WeniAuthViewMixin):
    """View mixin for Nexus routes consumed by the App IO."""

    authentication_classes = WENI_IO_AUTHENTICATION_CLASSES
    permission_classes = [HybridIOIdentityPermission, HybridIOProjectPermission]

    def get_scoped_project_uuid(self, path_project_uuid: Optional[str] = None) -> str:
        """Resolve project UUID for App IO hybrid auth.

        - JWT / Keycloak (``WeniAuthContext``): read exclusively from
          ``self.auth.project_uuid`` (403 when absent). Path may only match;
          it never overrides the claim/resolved scope.
        - External superuser token (no auth context): fall back to the path
          for compatibility until those callers are migrated.
        """
        if path_project_uuid is None:
            path_project_uuid = self.kwargs.get("project_uuid")

        auth = getattr(self.request, "auth", None)
        if isinstance(auth, WeniAuthContext):
            # Prefer the mixin accessor so missing project_uuid raises 403
            # the same way as Eliton's ``self.auth.project_uuid`` contract.
            auth_project_uuid = str(self.auth.project_uuid)
            if path_project_uuid and str(path_project_uuid) != auth_project_uuid:
                raise PermissionDenied("Project UUID does not match authenticated scope.")
            return auth_project_uuid

        if path_project_uuid:
            return str(path_project_uuid)

        raise PermissionDenied("project_uuid could not be resolved from the request.")
