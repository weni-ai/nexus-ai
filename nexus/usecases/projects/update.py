import copy

from nexus.event_driven.publisher.rabbitmq_publisher import RabbitMQPublisher
from nexus.usecases.projects.dto import UpdateProjectDTO, FeatureVersionDTO
from nexus.usecases.projects.get_by_uuid import get_project_by_uuid
from nexus.projects.models import Project, FeatureVersion
from nexus.projects.permissions import has_project_permission
from nexus.usecases import users
from nexus.events import event_manager

from django.forms.models import model_to_dict


def update_message(UpdateProjectDTO: UpdateProjectDTO):  # pragma: no cover

    publisher = RabbitMQPublisher()

    action = "UPDATE"
    entity = "NEXUS"
    user = UpdateProjectDTO.user_email
    project_uuid = UpdateProjectDTO.uuid

    message = {
        "action": action,
        "entity": entity,
        "user": user,
        "project_uuid": project_uuid,
        "brain_on": UpdateProjectDTO.brain_on
    }

    publisher.send_message(
        body=message,
        exchange="recent-activities.topic",
        routing_key="brain_status"
    )


class ProjectUpdateUseCase:

    def __init__(
        self,
        event_manager_notify=event_manager.notify
    ) -> None:
        self.event_manager_notify = event_manager_notify

    def update_project(
        self,
        UpdateProjectDTO: UpdateProjectDTO
    ) -> Project:

        project = get_project_by_uuid(UpdateProjectDTO.uuid)
        user = users.get_by_email(UpdateProjectDTO.user_email)

        old_project_data = copy.deepcopy(project)

        has_project_permission(
            user=user,
            project=project,
            method="patch"
        )

        for attr, value in UpdateProjectDTO.dict().items():
            setattr(project, attr, value)
            if attr == "brain_on":
                update_message(UpdateProjectDTO)
        project.save()

        new_project_data = project

        self.event_manager_notify(
            event="project_activity",
            project=project,
            action_type="U",
            old_project_data=old_project_data,
            new_project_data=new_project_data,
            user=user
        )

        return project


class UpdateFeatureVersionUseCase:

    def __init__(
        self,
        event_manager_notify=event_manager.notify
    ) -> None:
        self.event_manager_notify = event_manager_notify

    def update_feature_version(
        self,
        feature_version_dto: FeatureVersionDTO
    ) -> FeatureVersion:

        feature_version = FeatureVersion.objects.get(uuid=feature_version_dto.uuuid)
        old_feature_version_data = model_to_dict(feature_version)
        for attr, value in feature_version_dto.dict().items():
            setattr(feature_version, attr, value)

        feature_version.save()
        new_feature_version_data = model_to_dict(feature_version)

        self.event_manager_notify(
            event="feature_version",
            feature_version=feature_version,
            action_type="U",
            old_feature_version_data=old_feature_version_data,
            new_feature_version_data=new_feature_version_data
        )

        return feature_version
