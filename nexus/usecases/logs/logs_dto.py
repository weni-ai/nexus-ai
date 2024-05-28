from dataclasses import dataclass
from nexus.intelligences.models import Intelligence
from nexus.projects.models import Project
from nexus.users.models import User


@dataclass
class CreateRecentActivityDTO:
    action_type: str
    project: Project
    created_by: User
    intelligence: Intelligence
    action_details: dict = None
