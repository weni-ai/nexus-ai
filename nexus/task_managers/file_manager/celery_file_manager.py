import pickle

from django.core.exceptions import ObjectDoesNotExist

from nexus.task_managers import tasks
from nexus.task_managers import tasks_bedrock
from nexus.task_managers.file_database.file_database import FileDataBase

from nexus.projects.models import Project

from nexus.usecases.intelligences.intelligences_dto import ContentBaseFileDTO
from nexus.usecases.intelligences.create import CreateContentBaseFileUseCase
from nexus.usecases.projects.projects_use_case import ProjectsUseCase


class CeleryFileManager:

    def __init__(
        self,
        file_database: FileDataBase = None,
    ):
        self._file_database = file_database

    def upload_file(
        self,
        file: bytes,
        content_base_uuid: str,
        extension_file: str,
        user_email: str,
        load_type: str = None
    ):
        print("[+ 🦑 START Uploading file 🦑 +]")
        print("Pickling...")
        pickled_file = pickle.dumps(file)
        print("Finished pickling")
        print("[+++++++++++++++++++++++++++++++]")

        content_base_file_dto = ContentBaseFileDTO(
            file=file,
            user_email=user_email,
            content_base_uuid=content_base_uuid,
            extension_file=extension_file,
        )
        content_base_file = CreateContentBaseFileUseCase().create_content_base_file(content_base_file=content_base_file_dto)
        try:
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
            indexer_database = project.indexer_database
        except ObjectDoesNotExist:
            indexer_database = Project.SENTENX

        if indexer_database == Project.BEDROCK:
            print("[+ 🦑 Using BEDROCK 🦑 +]")
            if "pdf" in extension_file:
                tasks_bedrock.bedrock_upload_file(
                    pickled_file,
                    content_base_uuid,
                    user_email,
                    str(content_base_file.uuid),
                )
                return {"uuid": str(content_base_file.uuid), "extension_file": extension_file}

            tasks_bedrock.bedrock_upload_file.delay(
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
