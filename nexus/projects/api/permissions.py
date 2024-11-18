from rest_framework import permissions

from nexus.usecases.projects.projects_use_case import ProjectsUseCase

from nexus.projects.permissions import has_project_permission
from nexus.projects.models import ProjectAuth


class ProjectPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        try:
            project_uuid = view.kwargs["project_uuid"]
            project = ProjectsUseCase().get_by_uuid(project_uuid)
            return has_project_permission(
                user=request.user,
                project=project,
                method=request.method
            )
        except ProjectAuth.DoesNotExist:
            return False
