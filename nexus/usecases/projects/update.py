import copy

from nexus.event_driven.publisher.rabbitmq_publisher import RabbitMQPublisher
from nexus.events import event_manager, notify_async
from nexus.projects.models import IntegratedFeature, Project
from nexus.projects.permissions import has_project_permission
from nexus.usecases import users
from nexus.usecases.projects.dto import UpdateProjectDTO
from nexus.usecases.projects.get_by_uuid import get_project_by_uuid
from nexus.usecases.projects.retrieve import get_integrated_feature


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
        "brain_on": UpdateProjectDTO.brain_on,
    }

    publisher.send_message(body=message, exchange="recent-activities.topic", routing_key="brain_status")


class ProjectUpdateUseCase:
    def __init__(self, event_manager_notify=event_manager.notify) -> None:
        self.event_manager_notify = event_manager_notify

    def update_project(self, UpdateProjectDTO: UpdateProjectDTO) -> Project:
        project = get_project_by_uuid(UpdateProjectDTO.uuid)
        user = users.get_by_email(UpdateProjectDTO.user_email)

        old_project_data = copy.deepcopy(project)

        has_project_permission(user=user, project=project, method="patch")

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
            user=user,
        )

        # Fire cache invalidation event (async observer)
        notify_async(
            event="cache_invalidation:project",
            project=project,
        )

        return project


class UpdateIntegratedFeatureUseCase:
    def update_integrated_feature(self, consumer_msg: dict) -> IntegratedFeature:
        try:
            integrated_feature = get_integrated_feature(
                project_uuid=consumer_msg.get("project_uuid"), feature_uuid=consumer_msg.get("feature_uuid")
            )
        except IntegratedFeature.DoesNotExist:
            return None

        updated_version = consumer_msg.get("action")
        integrated_feature.current_version_setup = updated_version
        integrated_feature.save()

        return integrated_feature
