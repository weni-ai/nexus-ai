from unittest.mock import MagicMock, patch
from uuid import uuid4

import pendulum
from django.test import SimpleTestCase

from nexus.task_managers.ingestion.constants import STRATEGY_DIRECT_WITH_FALLBACK
from nexus.task_managers.ingestion.direct import (
    _wait_for_terminal_document_status,
    build_client_token,
    build_s3_uri,
    https_file_url_to_s3_uri,
)


class BuildClientTokenTest(SimpleTestCase):
    def _file(self, modified_at=None):
        created = pendulum.datetime(2026, 1, 1, tz="UTC")
        file_obj = MagicMock()
        file_obj.uuid = uuid4()
        file_obj.created_at = created
        file_obj.modified_at = modified_at
        return file_obj

    def test_stable_token_for_same_version(self):
        project_uuid = str(uuid4())
        content_base_file = self._file(modified_at=pendulum.datetime(2026, 5, 1, tz="UTC"))
        t1 = build_client_token(project_uuid, content_base_file)
        t2 = build_client_token(project_uuid, content_base_file)
        self.assertEqual(t1, t2)

    def test_token_changes_when_modified_at_changes(self):
        project_uuid = str(uuid4())
        file_a = self._file(modified_at=pendulum.datetime(2026, 5, 1, tz="UTC"))
        file_b = self._file(modified_at=pendulum.datetime(2026, 5, 2, tz="UTC"))
        file_b.uuid = file_a.uuid
        self.assertNotEqual(build_client_token(project_uuid, file_a), build_client_token(project_uuid, file_b))


class HttpsToS3UriTest(SimpleTestCase):
    def test_converts_regional_virtual_hosted_url(self):
        uri = https_file_url_to_s3_uri(
            "https://my-bucket.s3.us-east-1.amazonaws.com/cb-uuid/file.pdf",
            "my-bucket",
            "us-east-1",
        )
        self.assertEqual(uri, "s3://my-bucket/cb-uuid/file.pdf")

    def test_converts_global_virtual_hosted_url(self):
        uri = https_file_url_to_s3_uri(
            "https://weni-develop-bedrock.s3.amazonaws.com/cb-uuid%2Ffile%20name.pdf",
            "weni-develop-bedrock",
            "us-east-1",
        )
        self.assertEqual(uri, "s3://weni-develop-bedrock/cb-uuid/file%20name.pdf")

    def test_build_s3_uri_encodes_spaces(self):
        self.assertEqual(
            build_s3_uri("my-bucket", "cb/file name.pdf"),
            "s3://my-bucket/cb/file%20name.pdf",
        )

    def test_converts_path_style_url(self):
        uri = https_file_url_to_s3_uri(
            "https://s3.amazonaws.com/my-bucket/cb-uuid/file.pdf",
            "my-bucket",
            "us-east-1",
        )
        self.assertEqual(uri, "s3://my-bucket/cb-uuid/file.pdf")


class WaitForDocumentStatusTest(SimpleTestCase):
    @patch("nexus.task_managers.ingestion.direct.sleep")
    @patch("nexus.task_managers.ingestion.direct.settings")
    def test_polls_until_indexed(self, mock_settings, mock_sleep):
        mock_settings.BEDROCK_DIRECT_INGEST_POLL_INTERVAL_SECONDS = 1
        mock_settings.BEDROCK_DIRECT_INGEST_POLL_MAX_ATTEMPTS = 5
        file_database = MagicMock()
        file_database.get_knowledge_base_document_status.side_effect = ["IN_PROGRESS", "INDEXED"]

        status = _wait_for_terminal_document_status(
            file_database,
            "s3://bucket/cb/file.pdf",
            "STARTING",
        )

        self.assertEqual(status, "INDEXED")
        self.assertEqual(file_database.get_knowledge_base_document_status.call_count, 2)

    def test_returns_immediately_when_already_indexed(self):
        file_database = MagicMock()
        status = _wait_for_terminal_document_status(
            file_database,
            "s3://bucket/cb/file.pdf",
            "INDEXED",
        )
        self.assertEqual(status, "INDEXED")
        file_database.get_knowledge_base_document_status.assert_not_called()


class RouteFileIngestionTest(SimpleTestCase):
    @patch("nexus.task_managers.tasks_bedrock.ingest_file_direct")
    @patch("nexus.task_managers.tasks_bedrock.start_ingestion_job")
    @patch("nexus.task_managers.ingestion.router.IngestionStrategyResolver.resolve", return_value="job")
    def test_job_strategy_calls_start_ingestion_job(self, _resolve, mock_start, mock_direct):
        from nexus.task_managers.ingestion.router import route_file_ingestion

        project = MagicMock()
        route_file_ingestion(
            task_manager_uuid="tm-1",
            project=project,
            project_uuid="p-1",
            content_base_uuid="cb-1",
            content_base_file_uuid="f-1",
            s3_uri="s3://b/k",
        )
        mock_start.assert_called_once_with("tm-1", project_uuid="p-1")
        mock_direct.delay.assert_not_called()

    @patch("nexus.task_managers.tasks_bedrock.ingest_file_direct")
    @patch("nexus.task_managers.tasks_bedrock.start_ingestion_job")
    @patch(
        "nexus.task_managers.ingestion.router.IngestionStrategyResolver.resolve",
        return_value=STRATEGY_DIRECT_WITH_FALLBACK,
    )
    def test_direct_strategy_enqueues_celery_task(self, _resolve, mock_start, mock_direct):
        from nexus.task_managers.ingestion.router import route_file_ingestion

        project = MagicMock()
        route_file_ingestion(
            task_manager_uuid="tm-1",
            project=project,
            project_uuid="p-1",
            content_base_uuid="cb-1",
            content_base_file_uuid="f-1",
            s3_uri="s3://b/k",
        )
        mock_start.assert_not_called()
        mock_direct.delay.assert_called_once()
