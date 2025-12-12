from uuid import UUID

from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver
from nexus.event_domain.recent_activity.create import create_recent_activity
from nexus.event_domain.recent_activity.recent_activities_dto import CreateRecentActivityDTO
from nexus.intelligences.models import IntegratedIntelligence


def _update_comparison_fields(
    old_model_data: dict,
    new_model_data: dict,
):
    action_details = {}
    for key, old_value in old_model_data.items():
        new_value = new_model_data.get(key)
        if old_value != new_value:
            if isinstance(old_value, UUID):
                old_value = str(old_value)
            if isinstance(new_value, UUID):
                new_value = str(new_value)
            action_details[key] = {"old": old_value, "new": new_value}
    return action_details


@observer("action_activity")
class ActionsObserver(EventObserver):
    def perform(self, action, action_type: str, **kwargs) -> None:
        content_base = action.content_base
        intelligence = content_base.intelligence

        if action_type == "U":
            action_details = _update_comparison_fields(
                old_model_data=kwargs.get("values_before_update"), new_model_data=kwargs.get("values_after_update")
            )
        else:
            action_details = kwargs.get("action_details")

        integrated_intelligence = IntegratedIntelligence.objects.get(intelligence=intelligence)
        project = integrated_intelligence.project

        user = kwargs.get("user")
        if user is None:
            user = project.created_by

        create_recent_activity_dto = CreateRecentActivityDTO(
            action_type=action_type,
            project=project,
            created_by=user,
            intelligence=intelligence,
            action_details=action_details,
        )
        create_recent_activity(instance=action, dto=create_recent_activity_dto)
