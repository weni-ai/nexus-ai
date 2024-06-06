from dataclasses import dataclass
from nexus.intelligences.models import Intelligence
from nexus.projects.models import Project
from nexus.users.models import User
from nexus.orgs.models import Org


@dataclass
class CreateRecentActivityDTO:
    action_type: str
    project: Project
    created_by: User
    intelligence: Intelligence
    action_details: dict = None


@dataclass
class RecentActivitiesDTO:
    org: Org
    user: User
    entity_name: str
    action: str
    entity: str = "NEXUS"
