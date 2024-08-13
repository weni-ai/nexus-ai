from .get_by_uuid import get_project_by_uuid
from nexus.usecases import users
from nexus.projects import permissions
from nexus.projects.models import FeatureVersion, IntegratedFeatureVersion
from nexus.projects.exceptions import FeatureVersionDoesNotExist


def get_project(
        project_uuid: str,
        user_email: str
):
    project = get_project_by_uuid(project_uuid)
    user = users.get_by_email(user_email)

    permissions.has_project_permission(user, project, "GET")

    return project


class RetrieveFeatureVersion:
    def get(self, feature_version_uuid: str):
        try:
            return FeatureVersion.objects.get(uuid=feature_version_uuid)
        except FeatureVersion.DoesNotExist:
            raise FeatureVersionDoesNotExist(f"Feature Version with UUID: {feature_version_uuid} Does Not Exist")


class RetrieveIntegratedFeatureVersion:
    def get(self, project_uuid: str, feature_version_uuid):
        return IntegratedFeatureVersion.objects.get(
            feature_version__uuid=feature_version_uuid,
            project__uuid=project_uuid,
        )
