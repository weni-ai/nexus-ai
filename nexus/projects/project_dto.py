from dataclasses import dataclass

from nexus.users.models import User
from nexus.projects.models import Project, ProjectAuthorizationRole

@dataclass
class ProjectCreationDTO:
    uuid: str
    name: str
    org_uuid: str
    template_type_uuid: str
    is_template: bool
    brain_on: bool = False


@dataclass
class FlowConsumerDTO:
    action: str
    entity: str
    entity_name: str
    user_email: str
    flow_organization: str
    entity_uuid: str
    project_uuid: str


@dataclass
class ProjectAuthCreationDTO:
    uuid: str
    created_by: User
    project: Project
    role: ProjectAuthorizationRole
    user: User
