import pickle

from nexus.task_managers import tasks
from nexus.task_managers.file_database.file_database import FileDataBase

from nexus.usecases.intelligences.intelligences_dto import ContentBaseFileDTO
from nexus.usecases.intelligences.create import CreateContentBaseFileUseCase
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from nexus.events import event_manager

from nexus.projects.models import Project


class CeleryFileManager:

    def __init__(
        self,
        event_manager_notify=event_manager.notify,
        file_database: FileDataBase = None,
    ):
        self._file_database = file_database
        self.event_manager_notify = event_manager_notify

    def upload_file(
        self,
        file: bytes,
        content_base_uuid: str,
        extension_file: str,
        user_email: str,
        load_type: str = None
    ):
        pickled_file = pickle.dumps(file)

        content_base_file_dto = ContentBaseFileDTO(
            file=file,
            user_email=user_email,
            content_base_uuid=content_base_uuid,
            extension_file=extension_file,
        )
        content_base_file = CreateContentBaseFileUseCase(event_manager_notify=self.event_manager_notify).create_content_base_file(content_base_file=content_base_file_dto)
        project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)

        if project.indexer_database == Project.BEDROCK:
            print("[+ 🦑 Using BEDROCK 🦑 +]")
            tasks.bedrock_upload_file.delay(
                pickled_file,
                content_base_uuid,
                user_email,
                str(content_base_file.uuid),
            )
            return {"uuid": str(content_base_file.uuid), "extension_file": extension_file}

        tasks.upload_file.delay(
            pickled_file,
            content_base_uuid,
            extension_file,
            user_email, str(content_base_file.uuid),
            load_type
        )
        return {"uuid": str(content_base_file.uuid), "extension_file": extension_file}
