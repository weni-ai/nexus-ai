from nexus.projects.models import Project


def get_project_by_uuid(
    project_uuid: str
) -> Project:

    try:
        return Project.objects.get(uuid=project_uuid)
    except Project.DoesNotExist:
        raise Exception(f"[ ProjectsUseCase ] Project with uuid `{project_uuid}` does not exists!")
    except Exception as exception:
        raise Exception(f"[ ProjectsUseCase ] error: {str(exception)}")
