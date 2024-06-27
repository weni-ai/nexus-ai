from nexus.event_domain.recent_activity.recent_activities_dto import CreateRecentActivityDTO
from nexus.event_domain.recent_activity.create import create_recent_activity
from nexus.event_domain.event_observer import EventObserver
from nexus.intelligences.models import IntegratedIntelligence

from django.forms.models import model_to_dict


def _update_comparison_fields(
    old_model_data,
    new_model_data,
):
    old_model_dict = model_to_dict(old_model_data)
    new_model_dict = model_to_dict(new_model_data)

    action_details = {}
    for key, old_value in old_model_dict.items():
        new_value = new_model_dict.get(key)
        if old_value != new_value:
            action_details[key] = {'old': old_value, 'new': new_value}
    return action_details


class ProjectObserver(EventObserver):

    def __init__(
        self,
        recent_activity_message=create_recent_activity
    ):
        self.recent_activity_message = recent_activity_message

    def perform(
        self,
        project,
        user,
        action_type: str,
        **kwargs
    ):
        integrated_intelligence = IntegratedIntelligence.objects.filter(
            project__uuid=project.uuid
        ).first()
        action_details = kwargs.get('action_details', {})

        if action_type == "U":
            old_model_data = kwargs.get('old_project_data')
            new_model_data = kwargs.get('new_project_data')
            action_details = _update_comparison_fields(old_model_data, new_model_data)

        dto = CreateRecentActivityDTO(
            action_type=action_type,
            project=project,
            created_by=user,
            intelligence=integrated_intelligence.intelligence,
            action_details=action_details
        )

        create_recent_activity(project, dto=dto)
