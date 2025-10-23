import requests

from django.conf import settings

from rest_framework.permissions import SAFE_METHODS

from .exceptions import ProjectAuthorizationDenied
from .models import Project, ProjectAuth, ProjectAuthorizationRole

from nexus.users.models import User
from nexus.orgs.models import OrgAuth, Role


def _is_authorized_response(response):
    return response.status_code != 404


def _check_project_authorization(
    token: str,
    project_uuid: str,
    method: str
) -> bool:

    base_url = settings.PROJECT_AUTH_API_BASE_URL
    url = f"{base_url}/v2/projects/{project_uuid}/authorization"

    existing_roles = {
        "not_set": 0,
        "viewer": 1,
        "contributor": 2,
        "moderator": 3,
        "support": 4,
        "chat_user": 5
    }

    try:
        response = requests.get(
            url,
            headers={'Authorization': token}
        )

        if not _is_authorized_response(response):
            raise ProjectAuth.DoesNotExist(
                'You do not have permission to perform this action.'
            )

        if method.upper() in SAFE_METHODS:
            return True

        project_authorization = response.json().get('project_authorization')
        if project_authorization == existing_roles.get('moderator'):
            return True

        if project_authorization == existing_roles.get('contributor'):
            return method.upper() in ['POST', 'PUT', 'PATCH', 'DELETE']

        raise ProjectAuthorizationDenied(
            'You do not have permission to perform this action.'
        )

    except requests.RequestException as e:
        raise e


def has_external_general_project_permission(
    request,
    project_uuid,
    method: str
) -> bool:

    token = request.headers.get('Authorization')
    try:
        return _check_project_authorization(token, project_uuid, method)
    except (requests.RequestException, ProjectAuth.DoesNotExist):
        # Only fall back to internal check if there was a request error or no external auth
        try:
            project = Project.objects.get(uuid=project_uuid)
            return has_project_permission(request.user, project, method)
        except Project.DoesNotExist:
            return False


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
            return method.upper() in ['POST', 'PUT', 'PATCH', 'DELETE']

        raise ProjectAuthorizationDenied(
            'You do not have permission to perform this action.'
        )
    except ProjectAuth.DoesNotExist:  # pragma: no cover
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
