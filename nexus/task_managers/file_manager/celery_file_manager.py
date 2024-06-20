import msgpack

from nexus.task_managers import tasks
from nexus.task_managers.file_database.file_database import FileDataBase

from nexus.usecases.intelligences.intelligences_dto import ContentBaseFileDTO
from nexus.usecases.intelligences.create import CreateContentBaseFileUseCase

from nexus.events import event_manager


class CeleryFileManager:

    def __init__(
        self,
        file_database: FileDataBase,
        event_manager_notify=event_manager.notify
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
        packed_file = msgpack.packb(file, use_bin_type=True)

        content_base_file_dto = ContentBaseFileDTO(
            file=file,
            user_email=user_email,
            content_base_uuid=content_base_uuid,
            extension_file=extension_file,
        )
        content_base_file = CreateContentBaseFileUseCase(
            event_manager_notify=self.event_manager_notify
        ).create_content_base_file(content_base_file=content_base_file_dto)
        tasks.upload_file.delay(
            packed_file,
            content_base_uuid,
            extension_file,
            user_email, str(content_base_file.uuid),
            load_type
        )
        return {"uuid": str(content_base_file.uuid), "extension_file": extension_file}
