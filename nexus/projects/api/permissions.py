import requests
from django.conf import settings
from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import SAFE_METHODS

from nexus.projects.models import Project, ProjectAuth
from nexus.projects.permissions import (
    _is_authorized_response,
    get_user_auth,
    has_external_general_project_permission,
    is_admin,
)


class ProjectPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        uuids = {
            view.kwargs.get("project_uuid"),
            request.data.get("project"),
            request.data.get("project_uuid"),
            request.query_params.get("project"),
            request.query_params.get("project_uuid"),
        }
        uuids.discard(None)

        if not uuids:
            return False
        try:
            project_uuid = next(iter(uuids))

            return has_external_general_project_permission(
                request=request, project_uuid=project_uuid, method=request.method
            )
        except (ProjectAuth.DoesNotExist, StopIteration):
            return False
        except Exception as e:
            raise ValidationError({"detail": f"An error occurred: {str(e)}"}) from e


class ExternalTokenPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        authorization_header = request.headers.get("Authorization")

        if not authorization_header:
            return False

        token = authorization_header.split("Bearer")[1].strip()

        if token not in settings.EXTERNAL_SUPERUSERS_TOKENS:
            return False

        return True


class CombinedExternalProjectPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        external_token_permission = ExternalTokenPermission()
        if external_token_permission.has_permission(request, view):
            return True

        authorization_header = request.headers.get("Authorization")
        if authorization_header:
            project_permission = ProjectPermission()
            return project_permission.has_permission(request, view)

        return False


class GuardrailsConfigAdminPermission(permissions.BasePermission):
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        project_uuid = view.kwargs.get("project_uuid")
        if not project_uuid:
            return False

        if request.method.upper() in SAFE_METHODS:
            return has_external_general_project_permission(
                request=request,
                project_uuid=project_uuid,
                method=request.method,
            )

        authorization_header = request.headers.get("Authorization")
        if authorization_header:
            return _has_external_moderator_permission(request, project_uuid)

        try:
            project = Project.objects.get(uuid=project_uuid)
            auth = get_user_auth(request.user, project)
            return is_admin(auth)
        except (Project.DoesNotExist, ProjectAuth.DoesNotExist):
            return False


def _has_external_moderator_permission(request, project_uuid: str) -> bool:
    token = request.headers.get("Authorization")
    if not token:
        return False

    base_url = settings.PROJECT_AUTH_API_BASE_URL
    url = f"{base_url}/v2/projects/{project_uuid}/authorization"
    moderator_role = 3

    try:
        response = requests.get(url, headers={"Authorization": token})
        if not _is_authorized_response(response):
            return False
        data = response.json()
        return data.get("project_authorization") == moderator_role
    except requests.RequestException:
        return False
