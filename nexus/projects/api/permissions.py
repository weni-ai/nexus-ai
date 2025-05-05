from rest_framework import permissions
from rest_framework.exceptions import ValidationError

from nexus.usecases.projects.projects_use_case import ProjectsUseCase

from nexus.projects.permissions import has_project_permission
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
            project = ProjectsUseCase().get_by_uuid(project_uuid)

            return has_project_permission(
                user=request.user,
                project=project,
                method=request.method
            )
        except (ProjectAuth.DoesNotExist, StopIteration):
            return False
        except Exception as e:
            raise ValidationError({"detail": f"An error occurred: {str(e)}"})
