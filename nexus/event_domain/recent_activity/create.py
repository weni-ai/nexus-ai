from nexus.logs.models import RecentActivities

from .recent_activities_dto import CreateRecentActivityDTO
from .recent_activity_amq import publish_recent_activity_to_amq


def create_recent_activity(
    instance,
    dto: CreateRecentActivityDTO,
) -> RecentActivities:
    recent_activity = RecentActivities.objects.create(
        action_model=instance.__class__.__name__,
        action_type=dto.action_type,
        project=dto.project,
        created_by=dto.created_by,
        intelligence=dto.intelligence,
        action_details=dto.action_details,
    )
    publish_recent_activity_to_amq(recent_activity=recent_activity)
    return recent_activity
