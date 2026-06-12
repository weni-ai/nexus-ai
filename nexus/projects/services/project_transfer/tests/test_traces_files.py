from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from nexus.agents.models import AgentMessage, Team
from nexus.inline_agents.models import InlineAgentMessage
from nexus.projects.services.project_transfer.traces_files_collector import (
    MissingTracesBucketError,
    collect_trace_s3_objects,
    inline_trace_key,
    legacy_trace_key,
)
from nexus.projects.services.project_transfer.traces_files_constants import TRACE_TYPE_INLINE, TRACE_TYPE_LEGACY
from nexus.projects.services.project_transfer.traces_files_manifest import (
    TraceFilesManifestExporter,
    TraceFilesManifestImporter,
)
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class TraceFilesCollectorTestCase(TestCase):
    def setUp(self):
        self.project = ProjectFactory()

    @patch("nexus.projects.services.project_transfer.traces_files_collector.boto3.client")
    @patch.dict("os.environ", {"AWS_BEDROCK_INLINE_TRACES_BUCKET": "inline-traces-bucket"})
    @patch("nexus.projects.services.project_transfer.traces_files_collector.settings")
    def test_collects_inline_and_legacy_trace_objects(self, mock_settings, mock_boto_client):
        mock_settings.AWS_BEDROCK_BUCKET_NAME = "bedrock-bucket"
        mock_settings.AWS_BEDROCK_REGION_NAME = "us-east-1"

        inline_message = InlineAgentMessage.objects.create(
            project=self.project,
            text="hello",
            session_id="session-1",
            contact_urn="whatsapp:5511999999999",
            source_type="whatsapp",
            source="router",
        )
        legacy_message = AgentMessage.objects.create(
            project=self.project,
            team=Team.objects.create(external_id="agent-123", project=self.project),
            user_text="hi",
            agent_response="hello",
            contact_urn="whatsapp:5511888888888",
            session_id="session-2",
            source="router",
        )

        inline_key = inline_trace_key(str(self.project.uuid), str(inline_message.uuid))
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"Contents": [{"Key": inline_key}]}]
        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_boto_client.return_value = mock_s3

        objects = collect_trace_s3_objects(self.project)

        keys = {(obj.bucket, obj.key, obj.trace_type) for obj in objects}
        self.assertIn(
            (
                "inline-traces-bucket",
                inline_trace_key(str(self.project.uuid), str(inline_message.uuid)),
                TRACE_TYPE_INLINE,
            ),
            keys,
        )
        self.assertIn(
            (
                "bedrock-bucket",
                legacy_trace_key(str(self.project.uuid), str(legacy_message.uuid)),
                TRACE_TYPE_LEGACY,
            ),
            keys,
        )

    @patch.dict("os.environ", {}, clear=True)
    def test_inline_bucket_is_required_when_inline_traces_are_included(self):
        with self.assertRaises(MissingTracesBucketError):
            collect_trace_s3_objects(self.project, include_legacy=False)


class TraceFilesManifestTestCase(TestCase):
    def setUp(self):
        self.project = ProjectFactory()
        self.inline_message = InlineAgentMessage.objects.create(
            project=self.project,
            text="hello",
            session_id="session-1",
            contact_urn="whatsapp:5511999999999",
            source_type="whatsapp",
            source="router",
        )

    @patch("nexus.projects.services.project_transfer.traces_files_collector.boto3.client")
    @patch("nexus.projects.services.project_transfer.traces_files_manifest.boto3.client")
    @patch.dict("os.environ", {"AWS_BEDROCK_INLINE_TRACES_BUCKET": "inline-traces-bucket"})
    @patch("nexus.projects.services.project_transfer.traces_files_collector.settings")
    def test_exporter_builds_presigned_manifest(
        self,
        mock_settings,
        mock_manifest_boto_client,
        mock_collector_boto_client,
    ):
        mock_settings.AWS_BEDROCK_BUCKET_NAME = "bedrock-bucket"
        mock_settings.AWS_BEDROCK_REGION_NAME = "us-east-1"

        inline_key = inline_trace_key(str(self.project.uuid), str(self.inline_message.uuid))
        mock_collector_paginator = MagicMock()
        mock_collector_paginator.paginate.return_value = [{"Contents": [{"Key": inline_key}]}]
        mock_collector_s3 = MagicMock()
        mock_collector_s3.get_paginator.return_value = mock_collector_paginator
        mock_collector_boto_client.return_value = mock_collector_s3

        mock_manifest_s3 = MagicMock()
        mock_manifest_s3.generate_presigned_url.return_value = "https://signed.example/trace.jsonl"
        mock_manifest_boto_client.return_value = mock_manifest_s3

        manifest = TraceFilesManifestExporter(
            self.project,
            include_legacy=False,
        ).build_manifest()

        self.assertEqual(manifest["source_project_uuid"], str(self.project.uuid))
        self.assertEqual(len(manifest["objects"]), 1)
        self.assertEqual(
            manifest["objects"][0]["key"],
            inline_trace_key(str(self.project.uuid), str(self.inline_message.uuid)),
        )
        self.assertEqual(manifest["objects"][0]["trace_type"], TRACE_TYPE_INLINE)

    @patch("nexus.projects.services.project_transfer.traces_files_manifest.requests.get")
    @patch("nexus.projects.services.project_transfer.traces_files_manifest.boto3.client")
    def test_importer_remaps_project_uuid_in_destination_key(self, mock_boto_client, mock_requests_get):
        mock_response = MagicMock()
        mock_response.content = b"trace-bytes"
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response

        mock_s3 = MagicMock()
        mock_s3.head_object.side_effect = _client_error("404")
        mock_boto_client.return_value = mock_s3

        source_project_uuid = str(self.project.uuid)
        dest_project_uuid = str(uuid4())
        message_uuid = str(self.inline_message.uuid)
        manifest = {
            "schema_version": "1.0",
            "source_project_uuid": source_project_uuid,
            "objects": [
                {
                    "key": inline_trace_key(source_project_uuid, message_uuid),
                    "bucket": "inline-traces-bucket",
                    "trace_type": TRACE_TYPE_INLINE,
                    "presigned_url": "https://signed.example/trace.jsonl",
                }
            ],
        }

        TraceFilesManifestImporter.from_json(
            json.dumps(manifest),
            dest_inline_bucket="dest-inline-bucket",
            dest_project_uuid=dest_project_uuid,
        ).import_files()

        upload_args = mock_s3.upload_fileobj.call_args[0]
        self.assertEqual(upload_args[1], "dest-inline-bucket")
        self.assertEqual(
            upload_args[2],
            inline_trace_key(dest_project_uuid, message_uuid),
        )


def _client_error(code: str):
    from botocore.exceptions import ClientError

    return ClientError({"Error": {"Code": code, "Message": "not found"}}, "HeadObject")
