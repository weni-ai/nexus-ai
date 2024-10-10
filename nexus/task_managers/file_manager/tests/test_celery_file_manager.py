from django.test import TestCase

from nexus.task_managers.file_manager.celery_file_manager import CeleryFileManager
from nexus.task_managers.file_database.file_database import FileDataBase, FileResponseDTO
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.intelligences.create import create_base_brain_structure


class MockFileDataBase(FileDataBase):
    def add_file(self, file):
        return FileResponseDTO(status=200, file_url="mock_url", err=None, file_name="mock_file_name")


class TestCeleryFileManager(TestCase):

    def setUp(self) -> None:
        self.file_database = MockFileDataBase()
        self.project = ProjectFactory()
        self.integrated_intelligence = create_base_brain_structure(self.project)
        self.intelligence = self.integrated_intelligence.intelligence
        self.content_base = self.intelligence.contentbases.get()
        self.celery_file_manager = CeleryFileManager(file_database=self.file_database)
        self.email = self.content_base.created_by.email

    def test_upload_file(self):
        file = b'file'
        content_base_uuid = self.content_base.uuid
        extension_file = 'txt'
        user_email = self.email
        response = self.celery_file_manager.upload_file(file, content_base_uuid, extension_file, user_email)
        self.assertIsInstance(response, dict)
