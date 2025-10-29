from nexus.projects.exceptions import ProjectDoesNotExist
from nexus.projects.models import Project


def get_project_by_uuid(project_uuid: str) -> Project:
    try:
        return Project.objects.get(uuid=project_uuid)
    except Project.DoesNotExist as e:
        raise ProjectDoesNotExist(f"[ ProjectsUseCase ] Project with uuid `{project_uuid}` does not exists!") from e
