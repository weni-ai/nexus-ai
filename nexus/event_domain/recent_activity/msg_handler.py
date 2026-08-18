from nexus.event_domain.recent_activity.recent_activities_dto import RecentActivitiesDTO
from nexus.event_domain.recent_activity.recent_activity_amq import publish_external_recent_activity_to_amq
from nexus.orgs.models import Org
from nexus.users.models import User


def recent_activity_message(
    org: Org,
    user: User,
    entity_name: str,
    action: str,
    action_model: str = "Intelligence",
    intelligence_activity_message=None,
):  # pragma: no cover
    action_type_mapping = {
        "C": "CREATE",
        "U": "UPDATE",
        "D": "DELETE",
    }

    if action not in {"CREATE", "UPDATE", "DELETE"}:
        action = action_type_mapping.get(action, action)

    msg_dto = RecentActivitiesDTO(
        org=org,
        user=user,
        entity_name=entity_name,
        action=action,
        action_model=action_model,
    )
    publish_external_recent_activity_to_amq(msg_dto)
