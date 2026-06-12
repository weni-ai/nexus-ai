from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from nexus.inline_agents.models import InlineAgentMessage
from nexus.projects.services.project_transfer.traces_files_collector import (
    MissingTracesBucketError,
    collect_trace_s3_objects,
    inline_trace_key,
)
from nexus.projects.services.project_transfer.traces_files_constants import (
    DEFAULT_IMPORT_WORKERS,
    TRACE_TYPE_INLINE,
)
from nexus.projects.services.project_transfer.traces_files_manifest import TraceFilesManifestImporter
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class TraceFilesParallelImportTestCase(TestCase):
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

    @patch.dict("os.environ", {}, clear=True)
    def test_inline_bucket_is_required_for_inline_traces(self):
        with self.assertRaises(MissingTracesBucketError):
            collect_trace_s3_objects(self.project, include_legacy=False)

    @patch("nexus.projects.services.project_transfer.traces_files_manifest.requests.get")
    @patch("nexus.projects.services.project_transfer.traces_files_manifest._thread_s3_client")
    def test_parallel_import_processes_all_objects(self, mock_thread_s3_client, mock_requests_get):
        mock_response = MagicMock()
        mock_response.content = b"trace-bytes"
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response

        mock_s3 = MagicMock()
        mock_s3.head_object.side_effect = _client_error("404")
        mock_thread_s3_client.return_value = mock_s3

        source_project_uuid = str(self.project.uuid)
        keys = [
            inline_trace_key(source_project_uuid, str(uuid4()))
            for _ in range(5)
        ]
        manifest = {
            "schema_version": "1.0",
            "source_project_uuid": source_project_uuid,
            "objects": [
                {
                    "key": key,
                    "bucket": "inline-traces-bucket",
                    "trace_type": TRACE_TYPE_INLINE,
                    "presigned_url": f"https://signed.example/{index}",
                }
                for index, key in enumerate(keys)
            ],
        }

        progress_events: list[tuple[int, int, str, str]] = []

        def progress_callback(completed, total, key, status):
            progress_events.append((completed, total, key, status))

        result = TraceFilesManifestImporter.from_json(
            json.dumps(manifest),
            dest_inline_bucket="dest-inline-bucket",
            workers=3,
            progress_callback=progress_callback,
        ).import_files()

        self.assertEqual(result["stats"]["copied"], 5)
        self.assertEqual(result["stats"]["failed"], 0)
        self.assertEqual(mock_requests_get.call_count, 5)
        self.assertEqual(mock_s3.upload_fileobj.call_count, 5)
        self.assertEqual(len(progress_events), 5)
        self.assertEqual(progress_events[-1][0], 5)
        self.assertEqual(progress_events[-1][1], 5)

    @patch("nexus.projects.services.project_transfer.traces_files_manifest.requests.get")
    @patch("nexus.projects.services.project_transfer.traces_files_manifest._thread_s3_client")
    def test_importer_remaps_project_uuid_in_destination_key(self, mock_thread_s3_client, mock_requests_get):
        mock_response = MagicMock()
        mock_response.content = b"trace-bytes"
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response

        mock_s3 = MagicMock()
        mock_s3.head_object.side_effect = _client_error("404")
        mock_thread_s3_client.return_value = mock_s3

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
            workers=DEFAULT_IMPORT_WORKERS,
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
