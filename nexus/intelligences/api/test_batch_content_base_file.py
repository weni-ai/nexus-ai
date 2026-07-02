from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from nexus.projects.models import Project
from nexus.task_managers.models import ContentBaseFileTaskManager
from nexus.usecases.intelligences.create import create_base_brain_structure
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.usecases.orgs.tests.org_factory import OrgFactory


class BatchContentBaseFileViewsetTestCase(TestCase):
    def setUp(self):
        self.org = OrgFactory()
        self.project = self.org.projects.create(
            name="Bedrock Direct",
            indexer_database=Project.BEDROCK,
            bedrock_ingestion_strategy=Project.BEDROCK_INGESTION_DIRECT,
            created_by=self.org.created_by,
        )
        self.user = self.org.created_by
        self.project.authorizations.create(user=self.user, role=3)
        create_base_brain_structure(self.project)
        self.content_base = get_default_content_base_by_project(str(self.project.uuid))
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = reverse(
            "content-base-file-batch-create",
            kwargs={"content_base_uuid": str(self.content_base.uuid)},
        )
        self.progress_url = reverse(
            "content-base-file-batch-progress",
            kwargs={"content_base_uuid": str(self.content_base.uuid)},
        )

    def test_batch_progress_requires_file_uuids(self):
        response = self.client.post(self.progress_url, {}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("file_uuids", response.json())

    def test_batch_progress_returns_statuses(self):
        from nexus.intelligences.models import ContentBaseFile

        content_base_file = ContentBaseFile.objects.create(
            content_base=self.content_base,
            file_name="progress.txt",
            extension_file="txt",
            created_by=self.user,
        )
        ContentBaseFileTaskManager.objects.create(
            content_base_file=content_base_file,
            created_by=self.user,
            status=ContentBaseFileTaskManager.STATUS_PROCESSING,
        )

        response = self.client.post(
            self.progress_url,
            {"file_uuids": [str(content_base_file.uuid)]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        content = response.json()
        self.assertEqual(content["total"], 1)
        self.assertEqual(content["remaining"], 1)
        self.assertEqual(content["progress_percentage"], 0)
        self.assertFalse(content["is_complete"])
        self.assertEqual(content["status"], "processing")
        self.assertNotIn("files", content)

    def test_batch_create_requires_files(self):
        response = self.client.post(self.url, {}, format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "files is required")

    @patch("nexus.task_managers.file_manager.celery_file_manager.direct_ingest_batch_submit.delay")
    @patch("nexus.task_managers.file_database.bedrock.BedrockFileDatabase")
    def test_batch_create_uploads_multiple_files(self, mock_bedrock_cls, mock_batch_submit):
        mock_bedrock = MagicMock()
        mock_bedrock_cls.return_value = mock_bedrock
        mock_bedrock.multipart_upload.side_effect = [
            ("file-a.txt", "https://example.com/file-a.txt"),
            ("file-b.txt", "https://example.com/file-b.txt"),
        ]

        files = [
            SimpleUploadedFile("file-a.txt", b"content a"),
            SimpleUploadedFile("file-b.txt", b"content b"),
        ]
        response = self.client.post(
            self.url,
            {"files": files, "extension_file": "txt"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        content = response.json()
        self.assertEqual(len(content["files"]), 2)
        mock_batch_submit.assert_called_once()
        submitted_filenames = mock_batch_submit.call_args.args[2]
        self.assertEqual(submitted_filenames, ["file-a.txt", "file-b.txt"])

    @patch("nexus.task_managers.file_manager.celery_file_manager.direct_ingest_batch_submit.delay")
    @patch("nexus.task_managers.file_database.bedrock.BedrockFileDatabase")
    def test_batch_create_accepts_job_strategy(self, mock_bedrock_cls, mock_batch_submit):
        self.project.bedrock_ingestion_strategy = Project.BEDROCK_INGESTION_JOB
        self.project.save(update_fields=["bedrock_ingestion_strategy"])

        mock_bedrock = MagicMock()
        mock_bedrock_cls.return_value = mock_bedrock
        mock_bedrock.multipart_upload.return_value = ("file-a.txt", "https://example.com/file-a.txt")

        files = [SimpleUploadedFile("file-a.txt", b"content a")]
        response = self.client.post(
            self.url,
            {"files": files, "extension_file": "txt"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        mock_bedrock_cls.assert_called_with(
            project_uuid=str(self.project.uuid),
            force_direct_ingest=True,
        )
        mock_batch_submit.assert_called_once()
