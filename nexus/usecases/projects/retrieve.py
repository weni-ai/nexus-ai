from .get_by_uuid import get_project_by_uuid
from nexus.usecases import users
from nexus.projects import permissions
from nexus.projects.models import IntegratedFeature


def get_project(
        project_uuid: str,
        user_email: str
):
    project = get_project_by_uuid(project_uuid)
    user = users.get_by_email(user_email)

    permissions.has_project_permission(user, project, "GET")

    return project


def get_integrated_feature(
        project_uuid: str,
        feature_uuid: str
):

    integrated_feature = IntegratedFeature.objects.get(
        project__uuid=project_uuid,
        feature_uuid=feature_uuid
    )

    return integrated_feature
