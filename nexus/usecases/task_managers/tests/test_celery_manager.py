from django.test import TestCase
from uuid import uuid4

from nexus.usecases.task_managers.exceptions import (
    ContentBaseFileTaskManagerNotExists,
    ContentBaseTextTaskManagerNotExists
)
from nexus.task_managers.models import TaskManager
from .task_manager_factory import ContentBaseFileTaskManagerFactory, ContentBaseTextTaskManagerFactory
from ..celery_task_manager import CeleryTaskManagerUseCase


class CeleryTaskManagerUseCaseTest(TestCase):
    def setUp(self) -> None:
        self.task_manager_use_case = CeleryTaskManagerUseCase()
        self.content_base_file_task_manager = ContentBaseFileTaskManagerFactory()
        self.content_base_text_task_manager = ContentBaseTextTaskManagerFactory()

    def test_update_task_status(self):
        task_uuid = self.content_base_file_task_manager.uuid
        status = "SUCCESS"
        file_type = "file"
        task_manager = self.task_manager_use_case.update_task_status(task_uuid, status, file_type)

        task_manager = TaskManager.objects.get(uuid=task_uuid)
        self.assertEqual(task_manager.status, status)

    def test_contentbasebile_does_not_exist(self):
        task_uuid = str(uuid4())
        file_type = "file"
        with self.assertRaises(ContentBaseFileTaskManagerNotExists):
            self.task_manager_use_case.update_task_status(task_uuid, "SUCCESS", file_type)

    def test_contentbasetext_does_not_exist(self):
        task_uuid = str(uuid4())
        file_type = "text"
        with self.assertRaises(ContentBaseTextTaskManagerNotExists):
            self.task_manager_use_case.update_task_status(task_uuid, "SUCCESS", file_type)
