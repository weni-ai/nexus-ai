import pendulum

from nexus.intelligences.models import (
    ContentBaseFile,
    ContentBaseLink,
    ContentBaseText,
)
from nexus.task_managers.models import (
    ContentBaseFileTaskManager,
    ContentBaseLinkTaskManager,
    ContentBaseTextTaskManager,
    TaskManager,
)
from nexus.usecases.task_managers.exceptions import (
    ContentBaseFileTaskManagerNotExists,
    ContentBaseLinkTaskManagerNotExists,
    ContentBaseTextTaskManagerNotExists,
)


class CeleryTaskManagerUseCase:
    def _get_task_manager_func(self, file_type: str) -> callable:
        task_managers = {
            "file": self._get_content_base_file_task_manager,
            "text": self._get_content_base_text_task_manager,
            "link": self._get_content_base_link_task_manager,
        }
        return task_managers.get(file_type)

    def _get_content_base_link_task_manager(self, task_uuid: str):
        try:
            content_base_task_manager = ContentBaseLinkTaskManager.objects.get(uuid=task_uuid)
            return content_base_task_manager
        except ContentBaseLinkTaskManager.DoesNotExist as e:
            msg = f"[ CeleryTaskManagerUseCase:ContentBaseLinkTaskManager ] - {task_uuid} does not exist"
            raise ContentBaseLinkTaskManagerNotExists(msg) from e
        except Exception as exception:
            raise Exception(f"[ ContentBaseLink ] - ContentBaseLink error to get - error: `{exception}`") from exception

    def _get_content_base_file_task_manager(self, task_uuid: str):
        try:
            content_base_task_manager = ContentBaseFileTaskManager.objects.get(uuid=task_uuid)
            return content_base_task_manager
        except ContentBaseFileTaskManager.DoesNotExist as e:
            msg = f"[ CeleryTaskManagerUseCase:ContentBaseFileTaskManager ] - {task_uuid} does not exist"
            raise ContentBaseFileTaskManagerNotExists(msg) from e
        except Exception as exception:
            raise Exception(f"[ ContentBaseFile ] - ContentBaseFile error to get - error: `{exception}`") from exception

    def _get_content_base_text_task_manager(self, task_uuid: str):
        try:
            content_base_task_manager = ContentBaseTextTaskManager.objects.get(uuid=task_uuid)
            return content_base_task_manager
        except ContentBaseTextTaskManager.DoesNotExist as e:
            msg = f"[ CeleryTaskManagerUseCase:ContentBaseTextTaskManager ] - {task_uuid} does not exist"
            content_base_task_manager = ContentBaseFileTaskManager.objects.filter(uuid=task_uuid)
            if content_base_task_manager.exists():
                return content_base_task_manager.first()
            raise ContentBaseTextTaskManagerNotExists(msg) from e
        except Exception as exception:
            raise Exception(f"[ ContentBaseFile ] - ContentBaseFile error to get - error: `{exception}`") from exception

    def create_celery_task_manager(self, content_base_file: ContentBaseFile) -> ContentBaseFileTaskManager:
        content_base_task_manager = ContentBaseFileTaskManager.objects.create(
            status=ContentBaseFileTaskManager.STATUS_WAITING,
            created_by=content_base_file.created_by,
            end_at=pendulum.now(),
            content_base_file=content_base_file,
        )
        import logging

        logging.getLogger(__name__).info(
            "Creating ContentBaseFileTaskManager", extra={"uuid": str(content_base_task_manager.uuid)}
        )
        return content_base_task_manager

    def create_celery_text_file_manager(self, content_base_text: ContentBaseText) -> ContentBaseTextTaskManager:
        content_base_task_manager = ContentBaseTextTaskManager.objects.create(
            status=ContentBaseFileTaskManager.STATUS_WAITING,
            created_by=content_base_text.created_by,
            end_at=pendulum.now(),
            content_base_text=content_base_text,
        )
        import logging

        logging.getLogger(__name__).info(
            "Creating ContentBaseTextTaskManager", extra={"uuid": str(content_base_task_manager.uuid)}
        )
        return content_base_task_manager

    def get_task_manager_by_uuid(self, task_uuid, file_type: str) -> TaskManager:
        task_manager = self._get_task_manager_func(file_type)
        content_base_task_manager = task_manager(task_uuid=task_uuid)
        return content_base_task_manager

    def update_task_status(self, task_uuid, status, file_type):
        task_manager = self.get_task_manager_by_uuid(task_uuid=task_uuid, file_type=file_type)
        task_manager.status = status
        task_manager.end_at = pendulum.now()
        task_manager.save(update_fields=["end_at", "status"])

    def create_celery_link_manager(self, content_base_link: ContentBaseLink) -> ContentBaseLinkTaskManager:
        content_base_task_manager = ContentBaseLinkTaskManager.objects.create(
            status=ContentBaseLinkTaskManager.STATUS_WAITING,
            created_by=content_base_link.created_by,
            end_at=pendulum.now(),
            content_base_link=content_base_link,
        )
        import logging

        logging.getLogger(__name__).info(
            "Creating ContentBaseLinkTaskManager", extra={"uuid": str(content_base_task_manager.uuid)}
        )
        return content_base_task_manager
