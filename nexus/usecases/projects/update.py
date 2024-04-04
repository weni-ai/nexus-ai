from nexus.projects.models import Project
from nexus.usecases import users, intelligences
from nexus.orgs import permissions
from .dto import UpdateProjectDTO
from .get_by_uuid import get_project_by_uuid


def update_project(
    UpdateProjectDTO: UpdateProjectDTO
) -> Project:

    project = get_project_by_uuid(UpdateProjectDTO.uuid)
    org = project.org
    user = users.get_by_email(UpdateProjectDTO.user_email)

    has_permission = permissions.can_edit_intelligence_of_org(user, org)
    if not has_permission:
        raise intelligences.IntelligencePermissionDenied()

    for attr, value in UpdateProjectDTO.dict().items():
        setattr(project, attr, value)
    project.save()

    return project
