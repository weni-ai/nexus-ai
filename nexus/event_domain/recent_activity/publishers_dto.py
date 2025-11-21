from dataclasses import dataclass

from nexus.orgs.models import Org
from nexus.users.models import User


@dataclass
class RecentActivitiesDTO:
    org: Org
    user: User
    entity_name: str
    action: str
    entity: str = "NEXUS"
