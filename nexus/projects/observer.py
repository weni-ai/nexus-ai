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
        if str(old_value) != str(new_value):
            action_details[key] = {'old': str(old_value), 'new': str(new_value)}
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


class FeatureVersionObserver(EventObserver):

    def _updated_fields(
        self,
        old_feature_version_dict: dict,
        new_feature_version_dict: dict
    ):
        action_details = {}
        for key, old_value in old_feature_version_dict.items():
            new_value = new_feature_version_dict.get(key)
            if str(old_value) != str(new_value):
                action_details[key] = {'old': str(old_value), 'new': str(new_value)}
        return action_details

    # TODO: On update, all existing projects using the changed feature version should be updated.
    def perform(
        self,
        feature_version,
        action_type,
        **kwargs
    ):

        if action_type == "U":
            old_feature_version_data = kwargs.get('old_feature_version_data')
            new_feature_version_data = kwargs.get('new_feature_version_data')

            self._updated_fields(
                old_feature_version_data,
                new_feature_version_data
            )

        pass
