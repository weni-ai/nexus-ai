import pickle

from django.core.exceptions import ObjectDoesNotExist

from nexus.task_managers import tasks
from nexus.task_managers import tasks_bedrock
from nexus.task_managers.file_database.file_database import FileDataBase

from nexus.projects.models import Project

from nexus.usecases.intelligences.intelligences_dto import ContentBaseFileDTO
from nexus.usecases.intelligences.create import CreateContentBaseFileUseCase, CreateContentBaseTextUseCase
from nexus.usecases.projects.projects_use_case import ProjectsUseCase

from nexus.task_managers.tasks_bedrock import bedrock_upload_text_file, bedrock_send_link
from nexus.task_managers.tasks import upload_text_file, send_link
from nexus.usecases.intelligences.get_by_uuid import get_by_contentbase_uuid
from nexus.usecases.intelligences.intelligences_dto import (
    ContentBaseLinkDTO,
    ContentBaseDTO,
    ContentBaseTextDTO
)
from nexus.usecases.intelligences.create import CreateContentBaseLinkUseCase


class CeleryFileManager:

    def __init__(
        self,
        file_database: FileDataBase = None,
    ):
        self._file_database = file_database

    def upload_link(
        self,
        link: str,
        content_base_uuid: str,
        user_email: str,
    ):
        content_base = get_by_contentbase_uuid(content_base_uuid)
        link_dto = ContentBaseLinkDTO(
            link=link,
            user_email=user_email,
            content_base_uuid=str(content_base.uuid)
        )

        content_base_link = CreateContentBaseLinkUseCase().create_content_base_link(link_dto)
        try:
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
            indexer_database = project.indexer_database
        except ObjectDoesNotExist:
            indexer_database = Project.SENTENX

        if indexer_database == Project.BEDROCK:
            bedrock_send_link.delay(
                link=link,
                user_email=user_email,
                content_base_link_uuid=str(content_base_link.uuid)
            )
        else:
            send_link.delay(
                link=link,
                user_email=user_email,
                content_base_link_uuid=str(content_base_link.uuid)
            )
        return content_base_link

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
        content_base_file = CreateContentBaseFileUseCase().create_content_base_file(content_base_file=content_base_file_dto)
        try:
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
            indexer_database = project.indexer_database
        except ObjectDoesNotExist:
            indexer_database = Project.SENTENX

        if indexer_database == Project.BEDROCK:
            print("[+ 🦑 Using BEDROCK 🦑 +]")
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

    def upload_text(self, text, content_base_uuid, user_email):
        content_base = get_by_contentbase_uuid(content_base_uuid)
        cb_dto = ContentBaseDTO(
            uuid=content_base.uuid,
            title=content_base.title,
            intelligence_uuid=content_base.intelligence.uuid,
            created_by_email=content_base.created_by.email,
        )
        cbt_dto = ContentBaseTextDTO(
            text=text,
            content_base_uuid=content_base_uuid,
            user_email=user_email
        )
        content_base_text = CreateContentBaseTextUseCase().create_contentbasetext(
            content_base_dto=cb_dto,
            content_base_text_dto=cbt_dto
        )

        try:
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
            indexer_database = project.indexer_database
        except ObjectDoesNotExist:
            indexer_database = Project.SENTENX

        if indexer_database == Project.BEDROCK:
            bedrock_upload_text_file.delay(
                content_base_dto=cb_dto.__dict__,
                content_base_text_uuid=str(content_base_text.uuid),
                text=text
            )

        else:
            upload_text_file.delay(
                content_base_dto=cb_dto.__dict__,
                content_base_text_uuid=content_base_text.uuid,
                text=text
            )

        return content_base_text
