from rest_framework import permissions


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
