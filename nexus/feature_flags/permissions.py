from django.shortcuts import get_object_or_404
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView
from weni.feature_flags.shortcuts import is_feature_active

from nexus.projects.models import Project


class FeatureFlagPermission(BasePermission):
    """
    Permission to check if a feature flag is active for the project in the request.

    Set ``feature_flag_key`` on the view class.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        feature_key = getattr(view, "feature_flag_key", None)
        if not feature_key:
            return False

        project = self._get_project_from_request(request, view)
        if not project:
            return False

        user_email = request.user.email if request.user.is_authenticated else None
        return is_feature_active(feature_key, user=user_email, project=project.uuid)

    def _get_project_from_request(self, request: Request, view: APIView):
        project_uuid = (
            request.query_params.get("project_uuid")
            or request.data.get("project_uuid")
            or view.kwargs.get("project_uuid")
        )
        if project_uuid:
            return get_object_or_404(Project, uuid=project_uuid)
        return None
