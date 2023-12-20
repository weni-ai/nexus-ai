from .file_manager import FileManager
from nexus.usecases.content_base.content_base_dto import ContentBaseFileDTO
from nexus.usecases import users
from nexus.usecases.content_base.content_base_file import get_by_uuid as content_base_usecase
from nexus.task_manager.models import ContentBaseFileTaskManager
from nexus.task_manager.file_database.file_database import FileDataBase
from nexus.task_manager.tasks import add_file

class CeleryFileManager(FileManager):

    def __init__(self, file_database: FileDataBase):
        self._file_database = file_database

    def upload_file(self, file: bytes, content_base_uuid: str):
        content_base_file = content_base_usecase.get_by_uuid(content_base_uuid=content_base_uuid)
        task_manager = ContentBaseFileTaskManager.objects.create(
            status=ContentBaseFileTaskManager.STATUS_WAITING,
            created_by=content_base_file.created_by,
            content_base_file=content_base_file
        )
        content_base_file_dto = ContentBaseFileDTO(
            file=file,
            user_email=content_base_file.created_by.user_email,
            content_base_uuid=content_base_uuid,
            extension_file=content_base_file.extension_file,
            file_url=""
        )
        add_file.apply_async(args=[task_manager, content_base_file_dto, self._file_database])
        return task_manager.uuid
