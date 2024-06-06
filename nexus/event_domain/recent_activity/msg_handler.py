from nexus.orgs.models import Org
from nexus.users.models import User

from nexus.event_domain.recent_activity.external_activities import intelligence_activity_message
from nexus.event_domain.recent_activity.recent_activities_dto import RecentActivitiesDTO


def recent_activity_message(
    org: Org,
    user: User,
    entity_name: str,
    action: str,
    intelligence_activity_message=intelligence_activity_message,
):  # pragma: no cover
    msg_dto = RecentActivitiesDTO(
        org=org,
        user=user,
        entity_name=entity_name,
        action=action,
    )
    intelligence_activity_message(msg_dto)
