import os
from django.conf import settings

from nexus.usecases.intelligences.intelligences_dto import ContentBaseFileDTO
from nexus.usecases.intelligences.create import CreateContentBaseFileUseCase
from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase
from nexus.task_managers.models import ContentBaseFileTaskManager

from nexus.task_managers.file_database.file_database import FileDataBase
from nexus.task_managers.tasks import add_file

class CeleryFileManager:

    def __init__(self, file_database: FileDataBase):
        self._file_database = file_database

    def upload_file(self, file: bytes, content_base_uuid: str, extension_file: str, user_email: str):
        content_base_file_dto = ContentBaseFileDTO(
            file=file,
            user_email=user_email,
            content_base_uuid=content_base_uuid,
            extension_file=extension_file,
            file_url=""
        )
        
        destination_path = os.path.join(settings.STATIC_ROOT, file.name)
        with open(destination_path, 'wb') as destination_file:
            destination_file.write(file.read())
        content_base_file = CreateContentBaseFileUseCase().create_content_base_file(content_base_file=content_base_file_dto)
        task_manager = CeleryTaskManagerUseCase().create_celery_task_manager(content_base_file=content_base_file)
        print(f"[ FILEMANAGER] task_manager: {task_manager.uuid} - destination_path: {destination_path}")
        add_file.apply_async(args=[str(task_manager.uuid), destination_path])
        response = {
            "task_uuid": task_manager.uuid,
            "task_status": task_manager.status,
            "content_base": {
                "uuid": content_base_file.uuid,
                "extension_file": content_base_file.extension_file,
            }
        }
        return response
