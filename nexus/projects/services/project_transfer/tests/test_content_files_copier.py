from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import TestCase

from nexus.intelligences.models import ContentBaseFile, ContentBaseLink, ContentBaseText
from nexus.projects.models import Project
from nexus.projects.services.project_transfer.content_files_collector import (
    UnsupportedIndexerError,
    collect_bedrock_s3_objects,
    ensure_bedrock_project,
)
from nexus.projects.services.project_transfer.content_files_manifest import (
    ContentFilesManifestExporter,
    ContentFilesManifestImporter,
)
from nexus.projects.services.project_transfer.s3_object_resolver import (
    bedrock_metadata_key,
    bedrock_object_key,
    parse_s3_object_url,
    resolve_bedrock_key,
)
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory, IntegratedIntelligenceFactory


class S3ObjectResolverTestCase(TestCase):
    def test_parse_virtual_hosted_s3_url(self):
        bucket, key = parse_s3_object_url(
            "https://my-bucket.s3.us-east-1.amazonaws.com/cb-uuid/my-file-abc.pdf"
        )
        self.assertEqual(bucket, "my-bucket")
        self.assertEqual(key, "cb-uuid/my-file-abc.pdf")

    def test_resolve_bedrock_key_from_url(self):
        key = resolve_bedrock_key(
            file_url="https://bucket.s3.us-east-1.amazonaws.com/cb-uuid/file.pdf",
            content_base_uuid="cb-uuid",
            file_name="other.pdf",
        )
        self.assertEqual(key, "cb-uuid/file.pdf")

    def test_resolve_bedrock_key_fallback(self):
        key = resolve_bedrock_key(
            file_url=None,
            content_base_uuid="cb-uuid",
            file_name="file.pdf",
        )
        self.assertEqual(key, bedrock_object_key("cb-uuid", "file.pdf"))

    def test_bedrock_metadata_key(self):
        self.assertEqual(
            bedrock_metadata_key("cb-uuid", "file.pdf"),
            "cb-uuid/file.pdf.metadata.json",
        )


class ContentFilesCollectorTestCase(TestCase):
    def setUp(self):
        self.integrated_intelligence = IntegratedIntelligenceFactory()
        self.project = self.integrated_intelligence.project
        self.project.indexer_database = Project.BEDROCK
        self.project.save(update_fields=["indexer_database"])
        self.content_base = ContentBaseFactory(
            intelligence=self.integrated_intelligence.intelligence,
            created_by=self.project.created_by,
        )

    def test_sentenx_project_is_rejected(self):
        self.project.indexer_database = Project.SENTENX
        self.project.save(update_fields=["indexer_database"])

        with self.assertRaises(UnsupportedIndexerError):
            ensure_bedrock_project(self.project)

    def test_collects_file_text_and_link_objects(self):
        content_base_uuid = str(self.content_base.uuid)
        ContentBaseFile.objects.create(
            content_base=self.content_base,
            created_by=self.project.created_by,
            extension_file="pdf",
            file_name="doc.pdf",
            file=f"https://bedrock-bucket.s3.us-east-1.amazonaws.com/{content_base_uuid}/doc.pdf",
        )
        ContentBaseText.objects.create(
            content_base=self.content_base,
            created_by=self.project.created_by,
            text="hello",
            file_name="notes.txt",
            file=f"https://bedrock-bucket.s3.us-east-1.amazonaws.com/{content_base_uuid}/notes.txt",
        )
        ContentBaseLink.objects.create(
            content_base=self.content_base,
            created_by=self.project.created_by,
            link="https://example.com/page",
            name="page.md",
        )

        with patch("nexus.projects.services.project_transfer.content_files_collector.settings") as mock_settings:
            mock_settings.AWS_BEDROCK_BUCKET_NAME = "bedrock-bucket"
            objects = collect_bedrock_s3_objects(self.project, include_metadata=True)

        keys = {obj.key for obj in objects}
        self.assertIn(f"{content_base_uuid}/doc.pdf", keys)
        self.assertIn(f"{content_base_uuid}/doc.pdf.metadata.json", keys)
        self.assertIn(f"{content_base_uuid}/notes.txt", keys)
        self.assertIn(f"{content_base_uuid}/page.md", keys)


class ContentFilesManifestTestCase(TestCase):
    def setUp(self):
        self.integrated_intelligence = IntegratedIntelligenceFactory()
        self.project = self.integrated_intelligence.project
        self.project.indexer_database = Project.BEDROCK
        self.project.save(update_fields=["indexer_database"])
        self.content_base = ContentBaseFactory(
            intelligence=self.integrated_intelligence.intelligence,
            created_by=self.project.created_by,
        )
        content_base_uuid = str(self.content_base.uuid)
        ContentBaseFile.objects.create(
            content_base=self.content_base,
            created_by=self.project.created_by,
            extension_file="pdf",
            file_name="doc.pdf",
            file=f"https://bedrock-bucket.s3.us-east-1.amazonaws.com/{content_base_uuid}/doc.pdf",
        )

    @patch("nexus.projects.services.project_transfer.content_files_manifest.boto3.client")
    @patch("nexus.projects.services.project_transfer.content_files_collector.settings")
    def test_exporter_builds_presigned_manifest(self, mock_settings, mock_boto_client):
        mock_settings.AWS_BEDROCK_BUCKET_NAME = "bedrock-bucket"
        mock_settings.AWS_BEDROCK_REGION_NAME = "us-east-1"
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://signed.example/doc.pdf"
        mock_boto_client.return_value = mock_s3

        manifest = ContentFilesManifestExporter(self.project, include_metadata=False).build_manifest()

        self.assertEqual(manifest["source_project_uuid"], str(self.project.uuid))
        self.assertEqual(len(manifest["objects"]), 1)
        self.assertEqual(manifest["objects"][0]["key"], f"{self.content_base.uuid}/doc.pdf")
        self.assertEqual(manifest["objects"][0]["presigned_url"], "https://signed.example/doc.pdf")

    @patch("nexus.projects.services.project_transfer.content_files_manifest.requests.get")
    @patch("nexus.projects.services.project_transfer.content_files_manifest.boto3.client")
    def test_importer_downloads_and_uploads_with_same_key(self, mock_boto_client, mock_requests_get):
        mock_response = MagicMock()
        mock_response.content = b"file-bytes"
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response

        mock_s3 = MagicMock()
        mock_s3.head_object.side_effect = _client_error("404")
        mock_boto_client.return_value = mock_s3

        manifest = {
            "schema_version": "1.0",
            "objects": [
                {
                    "key": "cb-uuid/doc.pdf",
                    "presigned_url": "https://signed.example/doc.pdf",
                }
            ],
        }

        result = ContentFilesManifestImporter.from_json(
            json.dumps(manifest),
            dest_bucket="dest-bucket",
        ).import_files()

        mock_requests_get.assert_called_once_with("https://signed.example/doc.pdf", timeout=300)
        mock_s3.upload_fileobj.assert_called_once()
        upload_args = mock_s3.upload_fileobj.call_args[0]
        self.assertIsInstance(upload_args[0], BytesIO)
        self.assertEqual(upload_args[1], "dest-bucket")
        self.assertEqual(upload_args[2], "cb-uuid/doc.pdf")
        self.assertEqual(result["stats"]["copied"], 1)

    @patch("nexus.projects.services.project_transfer.content_files_manifest.boto3.client")
    def test_importer_dry_run_does_not_upload(self, mock_boto_client):
        manifest = {
            "schema_version": "1.0",
            "objects": [
                {
                    "key": "cb-uuid/doc.pdf",
                    "presigned_url": "https://signed.example/doc.pdf",
                }
            ],
        }

        result = ContentFilesManifestImporter.from_json(
            json.dumps(manifest),
            dest_bucket="dest-bucket",
            dry_run=True,
        ).import_files()

        mock_boto_client.return_value.upload_fileobj.assert_not_called()
        self.assertEqual(result["stats"]["copied"], 1)


def _client_error(code: str):
    from botocore.exceptions import ClientError

    return ClientError({"Error": {"Code": code, "Message": "not found"}}, "HeadObject")
