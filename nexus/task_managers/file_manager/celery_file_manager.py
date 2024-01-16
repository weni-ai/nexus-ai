import pickle

from nexus.task_managers import tasks
from nexus.task_managers.file_database.file_database import FileDataBase


class CeleryFileManager:

    def __init__(self, file_database: FileDataBase):
        self._file_database = file_database

    def upload_file(self, file: bytes, content_base_uuid: str, extension_file: str, user_email: str):
        pickled_file = pickle.dumps(file)
        tasks.upload_file.delay(pickled_file, content_base_uuid, extension_file, user_email)
        return {"message": "CREATED"}
