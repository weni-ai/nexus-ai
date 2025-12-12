import logging

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status as http_status

from nexus.projects.models import Project
from nexus.task_managers import tasks, tasks_bedrock
from nexus.task_managers.file_database.file_database import FileDataBase
from nexus.task_managers.tasks_bedrock import start_ingestion_job
from nexus.usecases.intelligences.create import CreateContentBaseFileUseCase
from nexus.usecases.intelligences.intelligences_dto import (
    ContentBaseFileDTO,
    UpdateContentBaseFileDTO,
)
from nexus.usecases.intelligences.update import UpdateContentBaseFileUseCase
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from nexus.usecases.task_managers.celery_task_manager import (
    CeleryTaskManagerUseCase,
)

logger = logging.getLogger(__name__)


class CeleryFileManager:
    def __init__(
        self,
        file_database: FileDataBase = None,
    ):
        self._file_database = file_database

    def add_file_to_s3(
        self,
        file: bytes,
        filename: str,
        content_base_uuid: str,
        extension_file: str,
        user_email: str,
    ):
        from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
        from nexus.task_managers.file_database.file_database import FileResponseDTO

        response = FileResponseDTO()
        try:
            content_base_file_dto = ContentBaseFileDTO(
                file=file,
                file_name=filename,
                user_email=user_email,
                content_base_uuid=content_base_uuid,
                extension_file=extension_file,
            )
            content_base_file = CreateContentBaseFileUseCase().create_content_base_file(
                content_base_file=content_base_file_dto
            )
            content_base_file_uuid = str(content_base_file.uuid)
            file_database = BedrockFileDatabase()
            file_name, file_url = file_database.multipart_upload(file, content_base_uuid, content_base_file_uuid)
            file_database.add_metadata_json_file(file_name, content_base_uuid, content_base_file_uuid)
            response = FileResponseDTO(
                status=0, file_url=file_url, file_name=file_name, content_base_file_uuid=content_base_file_uuid
            )

        except Exception as exception:
            response.status = 1
            response.err = str(exception)

        return response

    def upload_and_ingest_file(
        self,
        file: bytes,
        filename: str,
        content_base_uuid: str,
        extension_file: str,
        user_email: str,
    ) -> tuple[dict, int]:
        file_database_response = self.add_file_to_s3(
            file,
            filename,
            content_base_uuid,
            extension_file,
            user_email,
        )

        if file_database_response.status != 0:
            data = {"message": file_database_response.err}
            status = http_status.HTTP_500_INTERNAL_SERVER_ERROR
            return data, status

        content_base_file_dto = UpdateContentBaseFileDTO(
            file_url=file_database_response.file_url, file_name=file_database_response.file_name
        )
        content_base_file = UpdateContentBaseFileUseCase().update_content_base_file(
            content_base_file_uuid=file_database_response.content_base_file_uuid,
            user_email=user_email,
            update_content_base_file_dto=content_base_file_dto,
        )
        task_manager = CeleryTaskManagerUseCase().create_celery_task_manager(content_base_file=content_base_file)

        try:
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
            project_uuid = str(project.uuid)
        except Exception:
            project_uuid = None

        start_ingestion_job(str(task_manager.uuid), project_uuid=project_uuid)
        return {"uuid": str(content_base_file.uuid), "extension_file": extension_file}, http_status.HTTP_201_CREATED

    def upload_and_ingest_inline_file(
        self,
        file: bytes,
        filename: str,
        content_base_uuid: str,
        extension_file: str,
        user_email: str,
    ) -> tuple[dict, int]:
        file_database_response = self.add_file_to_s3(
            file,
            filename,
            content_base_uuid,
            extension_file,
            user_email,
        )

        if file_database_response.status != 0:
            data = {"message": file_database_response.err}
            status = http_status.HTTP_500_INTERNAL_SERVER_ERROR
            return data, status

        content_base_file_dto = UpdateContentBaseFileDTO(
            file_url=file_database_response.file_url, file_name=file_database_response.file_name
        )
        content_base_file = UpdateContentBaseFileUseCase().update_inline_content_base_file(
            content_base_file_uuid=file_database_response.content_base_file_uuid,
            user_email=user_email,
            update_content_base_file_dto=content_base_file_dto,
        )
        task_manager = CeleryTaskManagerUseCase().create_celery_task_manager(content_base_file=content_base_file)
        try:
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
            project_uuid = str(project.uuid)
        except Exception:
            project_uuid = None

        start_ingestion_job(str(task_manager.uuid), project_uuid=project_uuid)
        return {"uuid": str(content_base_file.uuid), "extension_file": extension_file}, http_status.HTTP_201_CREATED

    def upload_file(
        self,
        file: bytes,
        content_base_uuid: str,
        extension_file: str,
        user_email: str,
        load_type: str = None,
        filename: str = None,
    ):
        bytes_file = file.read()

        content_base_file_dto = ContentBaseFileDTO(
            file=file,
            file_name=filename,
            user_email=user_email,
            content_base_uuid=content_base_uuid,
            extension_file=extension_file,
        )
        content_base_file = CreateContentBaseFileUseCase().create_content_base_file(
            content_base_file=content_base_file_dto
        )
        try:
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
            indexer_database = project.indexer_database
        except ObjectDoesNotExist:
            indexer_database = Project.SENTENX

        if indexer_database == Project.BEDROCK:
            logger.info("Using BEDROCK for file upload")
            tasks_bedrock.bedrock_upload_file.delay(
                bytes_file, content_base_uuid, user_email, str(content_base_file.uuid), filename=filename
            )
            return {"uuid": str(content_base_file.uuid), "extension_file": extension_file}

        tasks.upload_file.delay(
            bytes_file,
            content_base_uuid,
            extension_file,
            user_email,
            str(content_base_file.uuid),
            load_type,
            filename=filename,
        )
        return {"uuid": str(content_base_file.uuid), "extension_file": extension_file}

    def upload_inline_file(
        self,
        file: bytes,
        content_base_uuid: str,
        extension_file: str,
        user_email: str,
        load_type: str = None,
        filename: str = None,
    ):
        bytes_file = file.read()

        content_base_file_dto = ContentBaseFileDTO(
            file=file,
            file_name=filename,
            user_email=user_email,
            content_base_uuid=content_base_uuid,
            extension_file=extension_file,
        )
        content_base_file = CreateContentBaseFileUseCase().create_content_base_file(
            content_base_file=content_base_file_dto
        )
        try:
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
            indexer_database = project.indexer_database
        except ObjectDoesNotExist:
            indexer_database = Project.SENTENX

        if indexer_database == Project.BEDROCK:
            logger.info("Using BEDROCK for inline file upload")
            tasks_bedrock.bedrock_upload_inline_file.delay(
                bytes_file, content_base_uuid, user_email, str(content_base_file.uuid), filename=filename
            )
            return {"uuid": str(content_base_file.uuid), "extension_file": extension_file}

        tasks.upload_sentenx_inline_file.delay(
            bytes_file,
            content_base_uuid,
            extension_file,
            user_email,
            str(content_base_file.uuid),
            load_type,
            filename=filename,
        )
        return {"uuid": str(content_base_file.uuid), "extension_file": extension_file}
