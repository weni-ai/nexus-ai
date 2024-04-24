from nexus.usecases import projects

from nexus.projects.models import ProjectAuth
from nexus.projects.project_dto import ProjectAuthCreationDTO

from nexus.users.models import User


class ProjectAuthUseCase:

    def auth_dto_from_dict(
        consumer_msg: dict
    ) -> ProjectAuthCreationDTO:

        role = consumer_msg.get("role")
        uuid = consumer_msg.get("uuid")

        if not role:
            raise ValueError("Role is required")
        if not uuid:
            raise ValueError("UUID is required")

        user, created = User.objects.get_or_create(consumer_msg.get("user"))

        project = projects.get_by_uuid(consumer_msg.get("project_uuid"))

        return ProjectAuthCreationDTO(
            uuid=str(uuid),
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
                print(f"[ProjectAuthUseCase] - Project auth updated: {project_auth.uuid}")
                return project_auth
        except ProjectAuth.DoesNotExist:
            project_auth = ProjectAuth.objects.create(
                uuid=auth_dto.uuid,
                project=auth_dto.project,
                user=auth_dto.user,
                role=auth_dto.role
            )
            print(f"[ProjectAuthUseCase] - Project auth created: {project_auth.uuid}")
            return project_auth
        except Exception as exception:
            raise exception
