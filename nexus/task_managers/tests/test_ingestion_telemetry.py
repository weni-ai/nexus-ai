import json
from unittest.mock import patch

from django.test import SimpleTestCase

from nexus.task_managers.ingestion.telemetry import log_ingestion_completed, log_ingestion_route_decision


class IngestionTelemetryTest(SimpleTestCase):
    @patch("nexus.task_managers.ingestion.telemetry.logger")
    def test_completed_log_is_single_line_json_without_extra(self, mock_logger):
        log_ingestion_completed(
            {
                "path": "direct",
                "strategy": "direct_with_fallback",
                "status": "success",
                "content_base_uuid": "cb-1",
                "file_uuid": "f-1",
                "project_uuid": "p-1",
                "document_type": "file",
            }
        )
        mock_logger.info.assert_called_once()
        args, kwargs = mock_logger.info.call_args
        self.assertNotIn("extra", kwargs)
        self.assertEqual(args[0], "%s %s")
        self.assertEqual(args[1], "ingestion.completed")
        payload = json.loads(args[2])
        self.assertEqual(payload["event"], "ingestion.completed")
        self.assertEqual(payload["path"], "direct")
        self.assertNotIn("file_content", payload)

    @patch("nexus.task_managers.ingestion.telemetry.logger")
    def test_route_decision_log(self, mock_logger):
        log_ingestion_route_decision(
            {
                "effective_strategy": "direct_with_fallback",
                "requested_strategy": "direct_with_fallback",
                "project_uuid": "p-1",
            }
        )
        mock_logger.info.assert_called_once()
        args, _kwargs = mock_logger.info.call_args
        self.assertEqual(args[1], "ingestion.route_decision")
        payload = json.loads(args[2])
        self.assertEqual(payload["effective_strategy"], "direct_with_fallback")
