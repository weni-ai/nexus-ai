from nexus.orgs.models import Org
from nexus.users.models import User

from nexus.usecases import event_driven


def recent_activity_message(
    org: Org,
    user: User,
    entity_name: str,
    action: str
):  # pragma: no cover
    print("ENTROU AQUI")
    msg_dto = event_driven.publishers_dto.RecentActivitiesDTO(
        org=org,
        user=user,
        entity_name=entity_name,
        action=action,
    )
    event_driven.recent_activities.intelligence_activity_message(msg_dto)
