from rest_framework.permissions import SAFE_METHODS

from .exceptions import ProjectAuthorizationDenied
from .models import Project, ProjectAuth, ProjectAuthorizationRole

from nexus.users.models import User


def get_user_auth(user: User, project: Project):
    return ProjectAuth.objects.get(user=user, project=project)


def is_admin(
    auth: ProjectAuth
) -> bool:
    return auth.role == ProjectAuthorizationRole.MODERATOR.value


def is_contributor(
    auth: ProjectAuth
) -> bool:
    return auth.role == ProjectAuthorizationRole.CONTRIBUTOR.value


def is_support(
    auth: ProjectAuth
) -> bool:
    return auth.role == ProjectAuthorizationRole.SUPPORT.value


def has_project_permission(
    auth: ProjectAuth,
    method: str
) -> bool:

    if method in SAFE_METHODS:
        return True

    if is_admin(auth):
        return True

    if is_contributor(auth):
        return method in ['PUT', 'PATCH', 'DELETE']

    raise ProjectAuthorizationDenied(
        'You do not have permission to perform this action.'
    )
