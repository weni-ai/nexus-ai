import copy
from django.conf import settings

from nexus.event_driven.publisher.rabbitmq_publisher import RabbitMQPublisher
from nexus.usecases.projects.dto import UpdateProjectDTO
from nexus.usecases.projects.get_by_uuid import get_project_by_uuid
from nexus.usecases.projects.retrieve import get_integrated_feature
from nexus.projects.models import Project, IntegratedFeature
from nexus.projects.permissions import has_project_permission
from nexus.usecases import users
from nexus.events import event_manager
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project

from nexus.task_managers.file_manager.celery_file_manager import CeleryFileManager
from nexus.task_managers.file_database.s3_file_database import s3FileDatabase


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

    def migrate_project(self, project_uuid: str, indexer_database: str, user_email: str):
        project = get_project_by_uuid(project_uuid)
        content_base = get_default_content_base_by_project(str(project.uuid))
        content_base_uuid = str(content_base.uuid)

        if indexer_database == Project.BEDROCK:
            project.indexer_database = Project.BEDROCK
            project.save()

            content_base = get_default_content_base_by_project(str(project.uuid))

            for file in content_base.contentbasefiles.all():
                self.migrate_file_to_bedrock(
                    type="file",
                    user_email=user_email,
                    filename=file.file_name,
                    file_ext=file.extension_file,
                    content_base_uuid=content_base_uuid)

            for text in content_base.contentbasetexts.all():
                self.migrate_file_to_bedrock(
                    type="text",
                    user_email=user_email,
                    filename=file,
                    content_base_uuid=content_base_uuid,
                    text=text
                )

            for link in content_base.contentbaselinks.all():
                self.migrate_file_to_bedrock(
                    type="link",
                    user_email=user_email,
                    filename=link.link,
                    content_base_uuid=content_base_uuid)

    def migrate_file_to_bedrock(self, type, content_base_uuid, user_email, filename, file_ext=None, text=None):

        bucket = settings.AWS_S3_BUCKET_NAME

        if type == "file":
            f = s3FileDatabase().s3_client.get_object(
                Bucket=bucket,
                Key=filename,
            )
            if f["ResponseMetadata"]["HTTPStatusCode"] == 200:
                file = f.get("Body").read()
                CeleryFileManager().upload_file(
                    file=file,
                    content_base_uuid=content_base_uuid,
                    extension_file=file_ext,
                    user_email=user_email
                )

        elif type == "link":
            CeleryFileManager().upload_link(
                link=filename,
                content_base_uuid=content_base_uuid,
                user_email=user_email
            )

        elif type == "text":
            CeleryFileManager().upload_text(
                text=text,
                content_base_uuid=content_base_uuid,
                user_email=user_email
            )

    def migrate_project_to_sentenx(self):
        pass


class UpdateIntegratedFeatureUseCase:

    def update_integrated_feature(
        self,
        consumer_msg: dict
    ) -> IntegratedFeature:

        try:
            integrated_feature = get_integrated_feature(
                project_uuid=consumer_msg.get('project_uuid'),
                feature_uuid=consumer_msg.get('feature_uuid')
            )
        except IntegratedFeature.DoesNotExist:
            return None

        updated_version = consumer_msg.get('action')
        integrated_feature.current_version_setup = updated_version
        integrated_feature.save()

        return integrated_feature
