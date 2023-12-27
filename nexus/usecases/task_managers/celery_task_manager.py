import pendulum

from nexus.task_managers.models import ContentBaseFileTaskManager
from nexus.intelligences.models import ContentBaseFile


class CeleryTaskManagerUseCase:

    def create_celery_task_manager(self, content_base_file: ContentBaseFile) -> ContentBaseFileTaskManager:
        content_base_task_manager = ContentBaseFileTaskManager.objects.create(
            status=ContentBaseFileTaskManager.STATUS_WAITING,
            created_by=content_base_file.created_by,
            end_at=pendulum.now(),
            content_base_file=content_base_file
        )
        print(f"[ CeleryTaskManagerUseCase ] - creating {content_base_task_manager.uuid}")
        return content_base_task_manager


    def get_task_manager_by_uuid(self, task_uuid) -> ContentBaseFileTaskManager:
        try:
            content_base_task_manager = ContentBaseFileTaskManager.objects.get(uuid=task_uuid)
        except ContentBaseFileTaskManager.DoesNotExist:
            print(f"[ CeleryTaskManagerUseCase ] - {task_uuid} does not exist")
            raise Exception(f"[ CeleryTaskManagerUseCase ] - {task_uuid} does not exist")
        except Exception as exception:
            raise Exception(f"[ ContentBaseFile ] - ContentBaseFile error to get - error: `{exception}`")
        return content_base_task_manager