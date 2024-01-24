import pickle

from nexus.task_managers import tasks
from nexus.task_managers.file_database.file_database import FileDataBase

from nexus.usecases.intelligences.intelligences_dto import ContentBaseFileDTO
from nexus.usecases.intelligences.create import CreateContentBaseFileUseCase


class CeleryFileManager:

    def __init__(self, file_database: FileDataBase):
        self._file_database = file_database

    def upload_file(self, file: bytes, content_base_uuid: str, extension_file: str, user_email: str):
        pickled_file = pickle.dumps(file)

        content_base_file_dto = ContentBaseFileDTO(
            file=file,
            user_email=user_email,
            content_base_uuid=content_base_uuid,
            extension_file=extension_file,
        )
        content_base_file = CreateContentBaseFileUseCase().create_content_base_file(content_base_file=content_base_file_dto)
        tasks.upload_file.delay(pickled_file, content_base_uuid, extension_file, user_email, str(content_base_file.uuid))
        return {"uuid": str(content_base_file.uuid),  "extension_file": extension_file}
