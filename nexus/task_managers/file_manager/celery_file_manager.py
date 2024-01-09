import os
import pickle
from django.conf import settings

from nexus.usecases.intelligences.intelligences_dto import ContentBaseFileDTO
from nexus.usecases.intelligences.create import CreateContentBaseFileUseCase
from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase
from nexus.task_managers.models import ContentBaseFileTaskManager

from nexus.task_managers.file_database.file_database import FileDataBase
# from nexus.task_managers.tasks import add_file, upload_file
from nexus.task_managers import tasks


class CeleryFileManager:

    def __init__(self, file_database: FileDataBase):
        self._file_database = file_database

    def upload_file(self, file: bytes, content_base_uuid: str, extension_file: str, user_email: str):
        pfile = pickle.dumps(file)
        tasks.upload_file.delay(pfile, content_base_uuid, extension_file, user_email)
        return {"message": "CREATED"}
