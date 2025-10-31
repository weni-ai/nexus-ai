from nexus.logs.models import RecentActivities

from .recent_activities_dto import CreateRecentActivityDTO


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
    return recent_activity
