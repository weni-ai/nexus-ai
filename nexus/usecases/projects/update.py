import copy

from nexus.event_driven.publisher.rabbitmq_publisher import RabbitMQPublisher
from .dto import UpdateProjectDTO
from .get_by_uuid import get_project_by_uuid
from nexus.projects.models import Project
from nexus.orgs import permissions
from nexus.usecases import users
from nexus.usecases.intelligences.exceptions import IntelligencePermissionDenied
from nexus.events import event_manager


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
        org = project.org
        user = users.get_by_email(UpdateProjectDTO.user_email)

        old_project_data = copy.deepcopy(project)

        has_permission = permissions.can_edit_intelligence_of_org(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

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
