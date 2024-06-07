from rest_framework.permissions import SAFE_METHODS

from .exceptions import ProjectAuthorizationDenied
from .models import Project, ProjectAuth, ProjectAuthorizationRole

from nexus.users.models import User
from nexus.orgs.models import OrgAuth, Role


def get_user_auth(
    user: User,
    project: Project
):
    auth = ProjectAuth.objects.filter(user=user, project=project).first()
    if auth:
        return auth

    org_auth = OrgAuth.objects.filter(user=user, org=project.org).first()
    if org_auth and org_auth.role == Role.ADMIN.value:
        return ProjectAuth.objects.create(
            user=user,
            project=project,
            role=ProjectAuthorizationRole.MODERATOR.value
        )

    raise ProjectAuth.DoesNotExist("User does not have authorization to access this project.")


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


def _has_project_general_permission(
    auth: ProjectAuth,
    method: str
) -> bool:
    try:
        if method.upper() in SAFE_METHODS:
            return True

        if is_admin(auth):
            return True

        if is_contributor(auth):
            return method.upper() in ['PUT', 'PATCH', 'DELETE']

        raise ProjectAuthorizationDenied(
            'You do not have permission to perform this action.'
        )
    except ProjectAuth.DoesNotExist:
        raise ProjectAuth.DoesNotExist(
            'You do not have permission to perform this action.'
        )


def has_project_permission(
    user: User,
    project: Project,
    method: str
) -> bool:
    auth = get_user_auth(user=user, project=project)
    return _has_project_general_permission(auth, method)
