from .publishers_dto import RecentActivitiesDTO
from nexus.orgs.models import Org
from nexus.users.models import User


def mock_recent_activity_message(
    recent_activities_dto: RecentActivitiesDTO
) -> None:
    pass


def mock_event_manager_notify(
    event: str,
    **kwargs
) -> None:
    pass


def mock_message_handler(
    org: Org,
    user: User,
    entity_name: str,
    action: str,
    **kwargs
) -> None:
    pass
