import json
from io import BytesIO
from unittest import TestCase
from unittest.mock import MagicMock, patch

from nexus.task_managers.file_database.knowledge_base_filters import (
    DEFAULT_KNOWLEDGE_BASE_VERSION,
    KB_VERSION_DRAFT,
    build_knowledge_base_filter,
)


class BuildKnowledgeBaseFilterTestCase(TestCase):
    @patch("nexus.task_managers.file_database.knowledge_base_filters.get_datasource_id", return_value="ds-123")
    def test_release_only_filter(self, _mock_datasource):
        result = build_knowledge_base_filter(
            content_base_uuid="cb-uuid",
            project_uuid="project-uuid",
            knowledge_base_version="1",
            include_draft=False,
        )

        self.assertEqual(
            result,
            {
                "andAll": [
                    {"equals": {"key": "contentBaseUuid", "value": "cb-uuid"}},
                    {"equals": {"key": "x-amz-bedrock-kb-data-source-id", "value": "ds-123"}},
                    {"equals": {"key": "version", "value": "1"}},
                ]
            },
        )

    @patch("nexus.task_managers.file_database.knowledge_base_filters.get_datasource_id", return_value="ds-123")
    def test_include_draft_filter(self, _mock_datasource):
        result = build_knowledge_base_filter(
            content_base_uuid="cb-uuid",
            project_uuid="project-uuid",
            knowledge_base_version="2",
            include_draft=True,
        )

        self.assertEqual(
            result,
            {
                "andAll": [
                    {"equals": {"key": "contentBaseUuid", "value": "cb-uuid"}},
                    {"equals": {"key": "x-amz-bedrock-kb-data-source-id", "value": "ds-123"}},
                    {
                        "orAll": [
                            {"equals": {"key": "version", "value": "2"}},
                            {"equals": {"key": "version", "value": KB_VERSION_DRAFT}},
                        ]
                    },
                ]
            },
        )

    def test_uses_explicit_data_source_id(self):
        result = build_knowledge_base_filter(
            content_base_uuid="cb-uuid",
            project_uuid=None,
            knowledge_base_version=DEFAULT_KNOWLEDGE_BASE_VERSION,
            include_draft=False,
            data_source_id="explicit-ds",
        )

        self.assertEqual(
            result["andAll"][1],
            {"equals": {"key": "x-amz-bedrock-kb-data-source-id", "value": "explicit-ds"}},
        )


class AddMetadataJsonFileVersionTestCase(TestCase):
    def test_metadata_includes_draft_version(self):
        from nexus.task_managers.file_database.bedrock import BedrockFileDatabase

        mock_s3 = MagicMock()
        bedrock = object.__new__(BedrockFileDatabase)
        bedrock.s3_client = mock_s3
        bedrock.bucket_name = "test-bucket"
        bedrock._build_s3_key = lambda content_base_uuid, filename: f"{content_base_uuid}/{filename}"

        bedrock.add_metadata_json_file("file.txt", "cb-uuid", "file-uuid")

        mock_s3.upload_fileobj.assert_called_once()
        uploaded_stream: BytesIO = mock_s3.upload_fileobj.call_args.args[0]
        payload = json.loads(uploaded_stream.getvalue().decode("utf-8"))
        self.assertEqual(payload["metadataAttributes"]["version"], KB_VERSION_DRAFT)
        self.assertEqual(payload["metadataAttributes"]["contentBaseUuid"], "cb-uuid")
        self.assertEqual(payload["metadataAttributes"]["fileUuid"], "file-uuid")
        self.assertEqual(payload["metadataAttributes"]["filename"], "file.txt")
