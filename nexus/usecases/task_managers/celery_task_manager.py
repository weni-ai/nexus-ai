import logging

import pendulum

from nexus.events import event_manager
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

logger = logging.getLogger(__name__)


def _already_succeeded_for_content(task_manager: TaskManager) -> bool:
    """True if another task for the same content already reached SUCCESS (e.g. re-ingest)."""
    if getattr(task_manager, "content_base_file_id", None):
        return (
            ContentBaseFileTaskManager.objects.filter(
                content_base_file_id=task_manager.content_base_file_id,
                status=TaskManager.STATUS_SUCCESS,
            )
            .exclude(pk=task_manager.pk)
            .exists()
        )
    if getattr(task_manager, "content_base_link_id", None):
        return (
            ContentBaseLinkTaskManager.objects.filter(
                content_base_link_id=task_manager.content_base_link_id,
                status=TaskManager.STATUS_SUCCESS,
            )
            .exclude(pk=task_manager.pk)
            .exists()
        )
    if getattr(task_manager, "content_base_text_id", None):
        return (
            ContentBaseTextTaskManager.objects.filter(
                content_base_text_id=task_manager.content_base_text_id,
                status=TaskManager.STATUS_SUCCESS,
            )
            .exclude(pk=task_manager.pk)
            .exists()
        )
    return False


def publish_ingest_success_create(task_manager: TaskManager) -> None:
    """
    Publish CREATE recent-activity for file/link when ingest reaches SUCCESS.

    Safe to call only on first transition to SUCCESS for this task (caller must guard).
    Skips if the content already had a successful ingest (re-index after edit).
    Failures must not emit CREATE — DELETE of a failed object remains allowed elsewhere.
    """
    if _already_succeeded_for_content(task_manager):
        logger.debug(
            "Skipping ingest-success CREATE: content already succeeded (task %s)",
            getattr(task_manager, "uuid", None),
        )
        return

    user = getattr(task_manager, "created_by", None)
    if user is None:
        logger.warning(
            "Skipping ingest-success change history: missing created_by for task %s",
            getattr(task_manager, "uuid", None),
        )
        return

    content_base_file = getattr(task_manager, "content_base_file", None)
    if content_base_file is not None:
        event_manager.notify(
            event="contentbase_file_activity",
            content_base_file=content_base_file,
            action_type="C",
            user=user,
            action_details={"old": "", "new": content_base_file.created_file_name},
        )
        return

    content_base_link = getattr(task_manager, "content_base_link", None)
    if content_base_link is not None:
        event_manager.notify(
            event="contentbase_link_activity",
            content_base_link=content_base_link,
            action_type="C",
            user=user,
            action_details={"old": "", "new": content_base_link.link},
        )
        return

    if getattr(task_manager, "content_base_text", None) is not None:
        return

    logger.warning(
        "Skipping ingest-success change history: task %s has no content relation",
        getattr(task_manager, "uuid", None),
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
        logger.info("Creating ContentBaseFileTaskManager", extra={"uuid": str(content_base_task_manager.uuid)})
        return content_base_task_manager

    def create_celery_text_file_manager(self, content_base_text: ContentBaseText) -> ContentBaseTextTaskManager:
        content_base_task_manager = ContentBaseTextTaskManager.objects.create(
            status=ContentBaseFileTaskManager.STATUS_WAITING,
            created_by=content_base_text.created_by,
            end_at=pendulum.now(),
            content_base_text=content_base_text,
        )
        logger.info("Creating ContentBaseTextTaskManager", extra={"uuid": str(content_base_task_manager.uuid)})
        return content_base_task_manager

    def get_task_manager_by_uuid(self, task_uuid, file_type: str) -> TaskManager:
        task_manager = self._get_task_manager_func(file_type)
        content_base_task_manager = task_manager(task_uuid=task_uuid)
        return content_base_task_manager

    def update_task_status(self, task_uuid, status, file_type):
        task_manager = self.get_task_manager_by_uuid(task_uuid=task_uuid, file_type=file_type)
        previous_status = task_manager.status
        task_manager.status = status
        task_manager.end_at = pendulum.now()
        task_manager.save(update_fields=["end_at", "status"])
        if status == TaskManager.STATUS_SUCCESS and previous_status != TaskManager.STATUS_SUCCESS:
            publish_ingest_success_create(task_manager)

    def create_celery_link_manager(self, content_base_link: ContentBaseLink) -> ContentBaseLinkTaskManager:
        content_base_task_manager = ContentBaseLinkTaskManager.objects.create(
            status=ContentBaseLinkTaskManager.STATUS_WAITING,
            created_by=content_base_link.created_by,
            end_at=pendulum.now(),
            content_base_link=content_base_link,
        )
        logger.info("Creating ContentBaseLinkTaskManager", extra={"uuid": str(content_base_task_manager.uuid)})
        return content_base_task_manager
