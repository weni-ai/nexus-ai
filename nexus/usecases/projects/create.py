from nexus.usecases import projects

from nexus.projects.models import ProjectAuth
from nexus.projects.project_dto import ProjectAuthCreationDTO

from nexus.users.models import User


class ProjectAuthUseCase:

    def auth_dto_from_dict(
        self,
        consumer_msg: dict
    ) -> ProjectAuthCreationDTO:
        role = consumer_msg.get("role")
        user_email = consumer_msg.get("user")
        project_uuid = consumer_msg.get("project_uuid")

        if not role:
            raise ValueError("Role is required")

        user, created = User.objects.get_or_create(email=user_email)

        project = projects.get_project_by_uuid(project_uuid=project_uuid)

        return ProjectAuthCreationDTO(
            user=user,
            project=project,
            role=role
        )

    def create_project_auth(
        self,
        consumer_msg: dict
    ) -> ProjectAuth:

        auth_dto = self.auth_dto_from_dict(consumer_msg)
        try:
            project_auth = ProjectAuth.objects.get(
                project=auth_dto.project,
                user=auth_dto.user
            )
            if project_auth.role != auth_dto.role:
                project_auth.role = auth_dto.role
                project_auth.save(update_fields=["role"])
                return project_auth
        except ProjectAuth.DoesNotExist:
            project_auth = ProjectAuth.objects.create(
                project=auth_dto.project,
                user=auth_dto.user,
                role=auth_dto.role
            )
            return project_auth
        except Exception as exception:
            raise exception
