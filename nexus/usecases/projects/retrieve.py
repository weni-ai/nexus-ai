from .get_by_uuid import get_project_by_uuid
from nexus.usecases import users
from nexus.orgs import permissions
from nexus.usecases.intelligences import IntelligencePermissionDenied


def get_project(
        project_uuid: str,
        user_email: str
):
    project = get_project_by_uuid(project_uuid)
    org = project.org
    user = users.get_by_email(user_email)

    has_permission = permissions.can_list_org_intelligences(user, org)
    if not has_permission:
        raise IntelligencePermissionDenied()

    return project
