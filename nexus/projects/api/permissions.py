from rest_framework import permissions
from rest_framework.exceptions import ValidationError

from nexus.projects.permissions import has_external_general_project_permission
from nexus.projects.models import ProjectAuth


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
                request=request,
                project_uuid=project_uuid,
                method=request.method
            )
        except (ProjectAuth.DoesNotExist, StopIteration):
            return False
        except Exception as e:
            raise ValidationError({"detail": f"An error occurred: {str(e)}"})
