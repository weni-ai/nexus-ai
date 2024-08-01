from nexus.usecases import projects

from nexus.projects.models import ProjectAuth, FeatureVersion
from nexus.projects.project_dto import ProjectAuthCreationDTO
from nexus.usecases.projects.dto import FeatureVersionDTO

from nexus.users.models import User

from nexus.projects.exceptions import ProjectDoesNotExist


class ProjectAuthUseCase:

    def auth_dto_from_dict(
        self,
        consumer_msg: dict
    ) -> ProjectAuthCreationDTO:
        role = consumer_msg.get("role")
        user_email = consumer_msg.get("user")
        project_uuid = consumer_msg.get("project")

        if not role:
            raise ValueError("Role is required")

        user, created = User.objects.get_or_create(email=user_email)

        try:
            project = projects.get_project_by_uuid(project_uuid=project_uuid)
        except ProjectDoesNotExist as e:
            raise e
        except Exception as e:
            raise e

        return ProjectAuthCreationDTO(
            user=user,
            project=project,
            role=role
        )

    def create_project_auth(
        self,
        consumer_msg: dict
    ) -> ProjectAuth:

        try:
            auth_dto = self.auth_dto_from_dict(consumer_msg)
            action = consumer_msg.get("action")  # create, update, delete

            project_auth = ProjectAuth.objects.get(
                project=auth_dto.project,
                user=auth_dto.user
            )

            if action == "delete":
                project_auth.delete()
                return project_auth

            if project_auth.role != auth_dto.role:
                project_auth.role = auth_dto.role
                project_auth.save(update_fields=["role"])
                return project_auth

            return project_auth

        except ProjectDoesNotExist as e:
            raise e

        except ProjectAuth.DoesNotExist:
            if action != "delete":
                project_auth = ProjectAuth.objects.create(
                    project=auth_dto.project,
                    user=auth_dto.user,
                    role=auth_dto.role
                )
                return project_auth
            raise ValueError("Project auth does not exists")
        except Exception as exception:
            raise exception


class CreateFeatureVersionUseCase:

    def create_feature_version(
        self,
        consumer_msg: dict
    ) -> bool:
        feature_version_dto = FeatureVersionDTO(
            uuid=consumer_msg.get("feature_version_uuid"),
            setup=consumer_msg.get("setup")
        )

        try:
            FeatureVersion.objects.create(
                uuid=feature_version_dto.uuid,
                setup=feature_version_dto.setup
            )
            return True
        except Exception as e:
            raise e
