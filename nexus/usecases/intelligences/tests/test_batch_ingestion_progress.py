from django.test import TestCase

from nexus.intelligences.models import ContentBaseFile
from nexus.task_managers.models import ContentBaseFileTaskManager
from nexus.usecases.intelligences.batch_ingestion_progress import BatchIngestionProgressUseCase
from nexus.usecases.intelligences.create import create_base_brain_structure
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.usecases.orgs.tests.org_factory import OrgFactory


class BatchIngestionProgressUseCaseTestCase(TestCase):
    def setUp(self):
        self.org = OrgFactory()
        self.user = self.org.created_by
        self.project = self.org.projects.create(name="Bedrock Direct", created_by=self.user)
        create_base_brain_structure(self.project)
        self.content_base = get_default_content_base_by_project(str(self.project.uuid))
        self.use_case = BatchIngestionProgressUseCase()

    def _create_file_with_status(self, filename: str, status: str) -> ContentBaseFile:
        content_base_file = ContentBaseFile.objects.create(
            content_base=self.content_base,
            file_name=filename,
            extension_file="txt",
            created_by=self.user,
        )
        ContentBaseFileTaskManager.objects.create(
            content_base_file=content_base_file,
            created_by=self.user,
            status=status,
        )
        return content_base_file

    def test_get_progress_returns_counts_and_file_statuses(self):
        file_success = self._create_file_with_status("a.txt", ContentBaseFileTaskManager.STATUS_SUCCESS)
        file_processing = self._create_file_with_status("b.txt", ContentBaseFileTaskManager.STATUS_PROCESSING)
        file_failed = self._create_file_with_status("c.txt", ContentBaseFileTaskManager.STATUS_FAIL)

        progress = self.use_case.get_progress(
            str(self.content_base.uuid),
            [str(file_success.uuid), str(file_processing.uuid), str(file_failed.uuid)],
        )

        self.assertEqual(progress["total"], 3)
        self.assertEqual(progress["completed"], 1)
        self.assertEqual(progress["remaining"], 1)
        self.assertEqual(progress["failed"], 1)
        self.assertEqual(progress["progress_percentage"], 33)
        self.assertFalse(progress["is_complete"])
        self.assertEqual(progress["status"], BatchIngestionProgressUseCase.BATCH_STATUS_PROCESSING)
        self.assertEqual(len(progress["failed_files"]), 1)

    def test_get_progress_returns_complete_batch(self):
        file_success_a = self._create_file_with_status("a.txt", ContentBaseFileTaskManager.STATUS_SUCCESS)
        file_success_b = self._create_file_with_status("b.txt", ContentBaseFileTaskManager.STATUS_SUCCESS)

        progress = self.use_case.get_progress(
            str(self.content_base.uuid),
            [str(file_success_a.uuid), str(file_success_b.uuid)],
        )

        self.assertEqual(progress["progress_percentage"], 100)
        self.assertTrue(progress["is_complete"])
        self.assertEqual(progress["status"], BatchIngestionProgressUseCase.BATCH_STATUS_SUCCESS)
        self.assertNotIn("failed_files", progress)

    def test_get_progress_raises_when_file_not_in_content_base(self):
        file = self._create_file_with_status("a.txt", ContentBaseFileTaskManager.STATUS_SUCCESS)

        with self.assertRaises(ContentBaseFile.DoesNotExist):
            self.use_case.get_progress(
                str(self.content_base.uuid), [str(file.uuid), "00000000-0000-0000-0000-000000000099"]
            )
