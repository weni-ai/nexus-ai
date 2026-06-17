from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from nexus.projects.models import Project
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase


@override_settings(
    AWS_BEDROCK_BUCKET_NAME="test-bucket",
    AWS_BEDROCK_KNOWLEDGE_BASE_ID="kb-id",
    AWS_BEDROCK_DATASOURCE_ID="ds-id",
    AWS_BEDROCK_REGION_NAME="us-east-1",
)
class BedrockDirectIngestionMethodsTestCase(SimpleTestCase):
    def setUp(self):
        self.content_base_uuid = "content-base-uuid"
        self.filename = "document-abc.txt"

    def _bedrock_with_mocks(self):
        bedrock = BedrockFileDatabase.__new__(BedrockFileDatabase)
        bedrock.bucket_name = "test-bucket"
        bedrock.knowledge_base_id = "kb-id"
        bedrock.data_source_id = "ds-id"
        bedrock.s3_key_prefix = ""
        bedrock.bedrock_agent = MagicMock()
        return bedrock

    def test_build_s3_uri(self):
        bedrock = self._bedrock_with_mocks()
        uri = bedrock._build_s3_uri(self.content_base_uuid, self.filename)
        self.assertEqual(uri, f"s3://test-bucket/{self.content_base_uuid}/{self.filename}")

    def test_direct_ingest_calls_aws_with_expected_payload(self):
        bedrock = self._bedrock_with_mocks()
        bedrock.bedrock_agent.ingest_knowledge_base_documents.return_value = {
            "documentDetails": [{"status": "PENDING"}]
        }

        result = bedrock.direct_ingest(self.content_base_uuid, self.filename)

        bedrock.bedrock_agent.ingest_knowledge_base_documents.assert_called_once_with(
            knowledgeBaseId="kb-id",
            dataSourceId="ds-id",
            documents=[
                {
                    "content": {
                        "dataSourceType": "S3",
                        "s3": {
                            "s3Location": {
                                "uri": f"s3://test-bucket/{self.content_base_uuid}/{self.filename}",
                            }
                        },
                    },
                    "metadata": {
                        "type": "S3_LOCATION",
                        "s3Location": {
                            "uri": (f"s3://test-bucket/{self.content_base_uuid}/" f"{self.filename}.metadata.json"),
                        },
                    },
                }
            ],
        )
        self.assertEqual(result, [{"status": "PENDING"}])

    def test_direct_ingest_batch_calls_aws_with_multiple_documents(self):
        bedrock = self._bedrock_with_mocks()
        filenames = ["document-a.txt", "document-b.txt"]
        bedrock.bedrock_agent.ingest_knowledge_base_documents.return_value = {
            "documentDetails": [{"status": "PENDING"}, {"status": "PENDING"}]
        }

        result = bedrock.direct_ingest_batch(self.content_base_uuid, filenames)

        call_kwargs = bedrock.bedrock_agent.ingest_knowledge_base_documents.call_args.kwargs
        self.assertEqual(len(call_kwargs["documents"]), 2)
        self.assertEqual(
            call_kwargs["documents"][0]["content"]["s3"]["s3Location"]["uri"],
            f"s3://test-bucket/{self.content_base_uuid}/{filenames[0]}",
        )
        self.assertEqual(result, [{"status": "PENDING"}, {"status": "PENDING"}])

    def test_direct_delete_calls_aws_with_expected_payload(self):
        bedrock = self._bedrock_with_mocks()
        bedrock.bedrock_agent.delete_knowledge_base_documents.return_value = {
            "documentDetails": [{"status": "DELETING"}]
        }

        result = bedrock.direct_delete(self.content_base_uuid, self.filename)

        bedrock.bedrock_agent.delete_knowledge_base_documents.assert_called_once_with(
            knowledgeBaseId="kb-id",
            dataSourceId="ds-id",
            documentIdentifiers=[
                {
                    "dataSourceType": "S3",
                    "s3": {"uri": f"s3://test-bucket/{self.content_base_uuid}/{self.filename}"},
                }
            ],
        )
        self.assertEqual(result, [{"status": "DELETING"}])

    def test_build_s3_uri_with_direct_ingest_prefix(self):
        bedrock = self._bedrock_with_mocks()
        bedrock.s3_key_prefix = "direct-ingest/"
        uri = bedrock._build_s3_uri(self.content_base_uuid, self.filename)
        self.assertEqual(
            uri,
            f"s3://test-bucket/direct-ingest/{self.content_base_uuid}/{self.filename}",
        )


@override_settings(
    AWS_BEDROCK_DIRECT_DATASOURCE_ID="direct-ds",
    AWS_BEDROCK_DIRECT_INGEST_S3_PREFIX="direct-ingest/",
)
class BedrockDirectIngestS3PrefixTestCase(SimpleTestCase):
    @patch("nexus.projects.models.Project.objects.get")
    def test_resolves_prefix_for_direct_strategy(self, mock_project_get):
        project = MagicMock()
        project.bedrock_ingestion_strategy = Project.BEDROCK_INGESTION_DIRECT
        mock_project_get.return_value = project

        bedrock = BedrockFileDatabase.__new__(BedrockFileDatabase)
        bedrock.s3_key_prefix = bedrock._resolve_s3_key_prefix("project-uuid")
        self.assertEqual(bedrock.s3_key_prefix, "direct-ingest/")
        self.assertEqual(
            bedrock._build_s3_key("cb-uuid", "file.txt"),
            "direct-ingest/cb-uuid/file.txt",
        )

    @patch("nexus.projects.models.Project.objects.get")
    def test_no_prefix_for_job_strategy(self, mock_project_get):
        project = MagicMock()
        project.bedrock_ingestion_strategy = Project.BEDROCK_INGESTION_JOB
        mock_project_get.return_value = project

        bedrock = BedrockFileDatabase.__new__(BedrockFileDatabase)
        self.assertEqual(bedrock._resolve_s3_key_prefix("project-uuid"), "")

    @override_settings(AWS_BEDROCK_DIRECT_DATASOURCE_ID="")
    @patch("nexus.projects.models.Project.objects.get")
    def test_no_prefix_when_direct_datasource_not_configured(self, mock_project_get):
        project = MagicMock()
        project.bedrock_ingestion_strategy = Project.BEDROCK_INGESTION_DIRECT
        mock_project_get.return_value = project

        bedrock = BedrockFileDatabase.__new__(BedrockFileDatabase)
        self.assertEqual(bedrock._resolve_s3_key_prefix("project-uuid"), "")


class TriggerBedrockIngestionTestCase(SimpleTestCase):
    def _project(self, strategy: str):
        project = MagicMock()
        project.bedrock_ingestion_strategy = strategy
        return project

    @patch("nexus.task_managers.tasks_bedrock.start_ingestion_job")
    @patch("nexus.task_managers.tasks_bedrock.Project.objects.get")
    def test_trigger_uses_job_strategy(self, mock_project_get, mock_start_ingestion_job):
        from nexus.task_managers.tasks_bedrock import trigger_bedrock_ingestion

        mock_project_get.return_value = self._project(Project.BEDROCK_INGESTION_JOB)
        trigger_bedrock_ingestion("", project_uuid="project-uuid")

        mock_start_ingestion_job.assert_called_once_with(
            "",
            file_type="file",
            post_delete=False,
            project_uuid="project-uuid",
        )

    @patch("nexus.task_managers.tasks_bedrock.direct_ingest")
    @patch("nexus.task_managers.tasks_bedrock.Project.objects.get")
    def test_trigger_uses_direct_ingest_for_upload(self, mock_project_get, mock_direct_ingest):
        from nexus.task_managers.tasks_bedrock import trigger_bedrock_ingestion

        mock_project_get.return_value = self._project(Project.BEDROCK_INGESTION_DIRECT)
        mock_direct_ingest.delay = MagicMock()
        trigger_bedrock_ingestion("task-uuid", file_type="file", project_uuid="project-uuid")

        mock_direct_ingest.delay.assert_called_once_with(
            "task-uuid",
            file_type="file",
            project_uuid="project-uuid",
        )

    @patch("nexus.task_managers.tasks_bedrock.direct_delete")
    @patch("nexus.task_managers.tasks_bedrock.Project.objects.get")
    def test_trigger_uses_direct_delete_for_post_delete(self, mock_project_get, mock_direct_delete):
        from nexus.task_managers.tasks_bedrock import trigger_bedrock_ingestion

        mock_project_get.return_value = self._project(Project.BEDROCK_INGESTION_DIRECT)
        mock_direct_delete.delay = MagicMock()
        trigger_bedrock_ingestion(
            "",
            post_delete=True,
            project_uuid="project-uuid",
            content_base_uuid="cb-uuid",
            filename="file.txt",
        )

        mock_direct_delete.delay.assert_called_once_with(
            "cb-uuid",
            "file.txt",
            "project-uuid",
        )

    @patch("nexus.task_managers.tasks_bedrock.start_ingestion_job")
    @patch("nexus.task_managers.tasks_bedrock.Project.objects.get")
    def test_trigger_uses_job_strategy_for_post_delete(self, mock_project_get, mock_start_ingestion_job):
        from nexus.task_managers.tasks_bedrock import trigger_bedrock_ingestion

        mock_project_get.return_value = self._project(Project.BEDROCK_INGESTION_JOB)
        trigger_bedrock_ingestion(
            "",
            post_delete=True,
            project_uuid="project-uuid",
            content_base_uuid="cb-uuid",
            filename="file.txt",
        )

        mock_start_ingestion_job.assert_called_once_with(
            "",
            file_type="file",
            post_delete=True,
            project_uuid="project-uuid",
        )


class StartIngestionJobTestCase(SimpleTestCase):
    @patch("nexus.task_managers.tasks_bedrock.CeleryTaskManagerUseCase")
    @patch("nexus.task_managers.tasks_bedrock.BedrockFileDatabase")
    @override_settings(BEDROCK_INGESTION_JOB_ENABLED=False)
    def test_start_ingestion_job_skips_when_disabled(self, mock_bedrock_cls, mock_task_manager_usecase_cls):
        from nexus.task_managers.models import TaskManager
        from nexus.task_managers.tasks_bedrock import start_ingestion_job

        task_manager_usecase = MagicMock()
        mock_task_manager_usecase_cls.return_value = task_manager_usecase

        start_ingestion_job("task-uuid", file_type="file")

        mock_bedrock_cls.assert_not_called()
        task_manager_usecase.update_task_status.assert_called_once_with(
            "task-uuid",
            TaskManager.STATUS_FAIL,
            "file",
        )

    @patch("nexus.task_managers.tasks_bedrock.BedrockFileDatabase")
    @override_settings(BEDROCK_INGESTION_JOB_ENABLED=False)
    def test_start_ingestion_job_skips_post_delete_when_disabled(self, mock_bedrock_cls):
        from nexus.task_managers.tasks_bedrock import start_ingestion_job

        start_ingestion_job("", post_delete=True, project_uuid="project-uuid")

        mock_bedrock_cls.assert_not_called()


class DirectIngestTaskTestCase(SimpleTestCase):
    @patch("nexus.task_managers.tasks_bedrock.direct_ingest.delay")
    @patch("nexus.task_managers.tasks_bedrock.BedrockFileDatabase")
    @patch("nexus.task_managers.tasks_bedrock.CeleryTaskManagerUseCase")
    def test_direct_ingest_task_marks_success_only_when_status_is_indexed(
        self, mock_task_manager_usecase_cls, mock_bedrock_cls, mock_direct_ingest_delay
    ):
        from nexus.task_managers.models import TaskManager
        from nexus.task_managers.tasks_bedrock import direct_ingest

        task_manager = MagicMock()
        content_base_file = MagicMock()
        content_base_file.content_base.uuid = "content-base-uuid"
        content_base_file.file_name = "test-file.txt"
        task_manager.content_base_file = content_base_file
        task_manager.content_base_text = None
        task_manager.content_base_link = None

        task_manager_usecase = MagicMock()
        task_manager_usecase.get_task_manager_by_uuid.return_value = task_manager
        mock_task_manager_usecase_cls.return_value = task_manager_usecase

        file_database = MagicMock()
        file_database.direct_ingest.return_value = [{"status": "INDEXED"}]
        mock_bedrock_cls.return_value = file_database

        direct_ingest("task-uuid", file_type="file")

        task_manager_usecase.update_task_status.assert_called_with(
            "task-uuid",
            TaskManager.status_map.get("COMPLETE"),
            "file",
        )
        file_database.search_data.assert_called_once()
        mock_direct_ingest_delay.assert_not_called()

    @patch("nexus.task_managers.tasks_bedrock.direct_ingest.delay")
    @patch("nexus.task_managers.tasks_bedrock.BedrockFileDatabase")
    @patch("nexus.task_managers.tasks_bedrock.CeleryTaskManagerUseCase")
    def test_direct_ingest_task_marks_fail_for_partially_indexed(
        self, mock_task_manager_usecase_cls, mock_bedrock_cls, mock_direct_ingest_delay
    ):
        from nexus.task_managers.models import TaskManager
        from nexus.task_managers.tasks_bedrock import direct_ingest

        task_manager = MagicMock()
        content_base_file = MagicMock()
        content_base_file.content_base.uuid = "content-base-uuid"
        content_base_file.file_name = "test-file.txt"
        task_manager.content_base_file = content_base_file
        task_manager.content_base_text = None
        task_manager.content_base_link = None

        task_manager_usecase = MagicMock()
        task_manager_usecase.get_task_manager_by_uuid.return_value = task_manager
        mock_task_manager_usecase_cls.return_value = task_manager_usecase

        file_database = MagicMock()
        file_database.direct_ingest.return_value = [{"status": "PARTIALLY_INDEXED"}]
        mock_bedrock_cls.return_value = file_database

        direct_ingest("task-uuid", file_type="file")

        task_manager_usecase.update_task_status.assert_called_with(
            "task-uuid",
            TaskManager.STATUS_FAIL,
            "file",
        )
        file_database.search_data.assert_not_called()
        mock_direct_ingest_delay.assert_not_called()

    @patch("nexus.task_managers.tasks_bedrock.direct_ingest.delay")
    @patch("nexus.task_managers.tasks_bedrock.BedrockFileDatabase")
    @patch("nexus.task_managers.tasks_bedrock.CeleryTaskManagerUseCase")
    def test_direct_ingest_task_retries_when_status_is_pending(
        self, mock_task_manager_usecase_cls, mock_bedrock_cls, mock_direct_ingest_delay
    ):
        from nexus.task_managers.models import TaskManager
        from nexus.task_managers.tasks_bedrock import direct_ingest

        task_manager = MagicMock()
        content_base_file = MagicMock()
        content_base_file.content_base.uuid = "content-base-uuid"
        content_base_file.file_name = "test-file.txt"
        task_manager.content_base_file = content_base_file
        task_manager.content_base_text = None
        task_manager.content_base_link = None

        task_manager_usecase = MagicMock()
        task_manager_usecase.get_task_manager_by_uuid.return_value = task_manager
        mock_task_manager_usecase_cls.return_value = task_manager_usecase

        file_database = MagicMock()
        file_database.direct_ingest.return_value = [{"status": "PENDING"}]
        mock_bedrock_cls.return_value = file_database

        direct_ingest("task-uuid", file_type="file")

        task_manager_usecase.update_task_status.assert_called_with(
            "task-uuid",
            TaskManager.status_map.get("IN_PROGRESS"),
            "file",
        )
        mock_direct_ingest_delay.assert_called_once_with(
            "task-uuid",
            file_type="file",
            project_uuid=None,
            waiting_time=30,
            ingest_submitted=True,
            poll_count=1,
        )
        file_database.search_data.assert_not_called()
        file_database.get_direct_ingest_document_status.assert_not_called()

    @patch("nexus.task_managers.tasks_bedrock.direct_ingest.delay")
    @patch("nexus.task_managers.tasks_bedrock.BedrockFileDatabase")
    @patch("nexus.task_managers.tasks_bedrock.CeleryTaskManagerUseCase")
    def test_direct_ingest_polls_status_without_resubmitting_ingest(
        self, mock_task_manager_usecase_cls, mock_bedrock_cls, mock_direct_ingest_delay
    ):
        from nexus.task_managers.models import TaskManager
        from nexus.task_managers.tasks_bedrock import direct_ingest

        task_manager = MagicMock()
        content_base_file = MagicMock()
        content_base_file.content_base.uuid = "content-base-uuid"
        content_base_file.file_name = "test-file.txt"
        task_manager.content_base_file = content_base_file
        task_manager.content_base_text = None
        task_manager.content_base_link = None

        task_manager_usecase = MagicMock()
        task_manager_usecase.get_task_manager_by_uuid.return_value = task_manager
        mock_task_manager_usecase_cls.return_value = task_manager_usecase

        file_database = MagicMock()
        file_database.get_direct_ingest_document_status.return_value = [{"status": "INDEXED"}]
        mock_bedrock_cls.return_value = file_database

        direct_ingest("task-uuid", file_type="file", ingest_submitted=True, poll_count=3)

        file_database.direct_ingest.assert_not_called()
        file_database.get_direct_ingest_document_status.assert_called_once()
        task_manager_usecase.update_task_status.assert_called_with(
            "task-uuid",
            TaskManager.status_map.get("COMPLETE"),
            "file",
        )
        mock_direct_ingest_delay.assert_not_called()


class DirectIngestBatchSubmitTestCase(SimpleTestCase):
    @patch("nexus.task_managers.tasks_bedrock.direct_ingest")
    @patch("nexus.task_managers.tasks_bedrock.BedrockFileDatabase")
    def test_direct_ingest_batch_submit_chunks_and_schedules_polls(self, mock_bedrock_cls, mock_direct_ingest):
        from nexus.task_managers.tasks_bedrock import direct_ingest_batch_submit

        mock_direct_ingest.delay = MagicMock()
        file_database = MagicMock()
        mock_bedrock_cls.return_value = file_database

        filenames = [f"file-{index}.txt" for index in range(3)]
        task_manager_uuids = [f"task-{index}" for index in range(3)]

        direct_ingest_batch_submit(
            task_manager_uuids,
            "content-base-uuid",
            filenames,
            project_uuid="project-uuid",
        )

        file_database.direct_ingest_batch.assert_called_once_with("content-base-uuid", filenames)
        self.assertEqual(mock_direct_ingest.delay.call_count, 3)
        mock_direct_ingest.delay.assert_any_call(
            "task-0",
            file_type="file",
            project_uuid="project-uuid",
            ingest_submitted=True,
            poll_count=0,
        )


@override_settings(
    AWS_BEDROCK_DATASOURCE_ID="default-ds",
    AWS_BEDROCK_LARGE_DATASOURCE_ID="large-ds",
    AWS_BEDROCK_DIRECT_DATASOURCE_ID="direct-ds",
    PROJECTS_WITH_LARGE_DATASOURCE=["large-project"],
)
class GetDatasourceIdTestCase(SimpleTestCase):
    @patch("nexus.projects.models.Project.objects.get")
    def test_returns_direct_datasource_for_direct_strategy(self, mock_project_get):
        from nexus.utils import get_datasource_id

        project = MagicMock()
        project.bedrock_ingestion_strategy = Project.BEDROCK_INGESTION_DIRECT
        mock_project_get.return_value = project

        self.assertEqual(get_datasource_id("project-uuid"), "direct-ds")

    @patch("nexus.projects.models.Project.objects.get")
    def test_returns_default_datasource_for_job_strategy(self, mock_project_get):
        from nexus.utils import get_datasource_id

        project = MagicMock()
        project.bedrock_ingestion_strategy = Project.BEDROCK_INGESTION_JOB
        mock_project_get.return_value = project

        self.assertEqual(get_datasource_id("project-uuid"), "default-ds")

    def test_returns_large_datasource_for_configured_project(self):
        from nexus.utils import get_datasource_id

        self.assertEqual(get_datasource_id("large-project"), "large-ds")
