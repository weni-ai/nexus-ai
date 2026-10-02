from unittest.mock import MagicMock, patch
from uuid import uuid4

import requests
from django.test import TestCase, override_settings

from nexus.projects.models import Project
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from scripts.sync_project_timezones import (
    ProjectClient,
    apply_after_uuid,
    fetch_page_with_retry,
    prepare_page_updates,
    sort_results_by_uuid,
    sync_page,
)


class ProjectClientTestCase(TestCase):
    @override_settings(CONNECT_REST_ENDPOINT="https://connect.example", PROJECTS_API_TOKEN="secret")
    @patch("scripts.sync_project_timezones.requests.get")
    def test_paginated_request_uses_token_and_ordering(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [], "next": None, "count": 0}
        mock_get.return_value = mock_response

        payload = ProjectClient().get_projects_paginated(page=2, page_size=50)

        self.assertEqual(payload["count"], 0)
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], "https://connect.example/v2/internals/connect/projects")
        self.assertEqual(kwargs["params"], {"page": 2, "page_size": 50, "ordering": "uuid"})
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")
        mock_response.raise_for_status.assert_called_once()

    @override_settings(CONNECT_REST_ENDPOINT="https://connect.example", PROJECTS_API_TOKEN="secret")
    @patch("scripts.sync_project_timezones.sentry_sdk.capture_exception")
    @patch("scripts.sync_project_timezones.requests.get")
    def test_paginated_request_raises_and_captures(self, mock_get, mock_capture):
        mock_get.side_effect = requests.RequestException("boom")

        with self.assertRaises(requests.RequestException):
            ProjectClient().get_projects_paginated(page=1)

        mock_capture.assert_called_once()

    @override_settings(
        CONNECT_REST_ENDPOINT="https://connect.example/",
        PROJECTS_API_BASE_URL="https://projects.example",
        PROJECTS_API_TOKEN=None,
    )
    @patch("nexus.internals.InternalAuthentication")
    def test_uses_internal_auth_and_base_url_override(self, mock_auth_cls):
        mock_auth = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_auth.make_request_with_retry.return_value = mock_response
        mock_auth_cls.return_value = mock_auth

        payload = ProjectClient().get_projects_paginated(page=1, page_size=10)

        self.assertEqual(payload, {"results": []})
        mock_auth.make_request_with_retry.assert_called_once()
        args, kwargs = mock_auth.make_request_with_retry.call_args
        self.assertEqual(args[0], "GET")
        self.assertEqual(args[1], "https://projects.example/v2/internals/connect/projects")
        self.assertEqual(kwargs["params"]["page"], 1)


class SyncProjectTimezonesLoopTestCase(TestCase):
    def setUp(self):
        self.keep = ProjectFactory(timezone="America/Sao_Paulo", project_auth=None)
        self.change = ProjectFactory(timezone=None, project_auth=None)
        self.same = ProjectFactory(timezone="America/Manaus", project_auth=None)

    def test_sort_and_after_uuid_resume(self):
        first = str(uuid4())
        second = str(uuid4())
        low, high = sorted([first, second])
        rows = [{"uuid": high, "timezone": "UTC"}, {"uuid": low, "timezone": "UTC"}]
        ordered = sort_results_by_uuid(rows)
        self.assertEqual([row["uuid"] for row in ordered], [low, high])
        skipped = apply_after_uuid(ordered, low)
        self.assertEqual([row["uuid"] for row in skipped], [high])

    def test_prepare_ignores_missing_empty_and_unchanged(self):
        missing_uuid = str(uuid4())
        rows = [
            {"uuid": str(self.change.uuid), "timezone": "America/Recife"},
            {"uuid": str(self.same.uuid), "timezone": "America/Manaus"},
            {"uuid": missing_uuid, "timezone": "UTC"},
            {"uuid": str(self.keep.uuid), "timezone": None},
            {"timezone": "UTC"},
        ]
        local = {
            str(self.change.uuid): self.change,
            str(self.same.uuid): self.same,
            str(self.keep.uuid): self.keep,
        }
        result = prepare_page_updates(sort_results_by_uuid(rows), local)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.skipped_missing, 1)
        self.assertEqual(result.skipped_unchanged, 1)
        self.assertGreaterEqual(result.skipped_empty, 1)
        self.assertEqual(result.to_update[0].timezone, "America/Recife")

    def test_sync_page_bulk_updates_only_changed(self):
        missing_uuid = str(uuid4())
        rows = [
            {"uuid": str(self.change.uuid), "timezone": "America/Recife"},
            {"uuid": str(self.same.uuid), "timezone": "America/Manaus"},
            {"uuid": missing_uuid, "timezone": "UTC"},
        ]
        result = sync_page(rows, project_model=Project, dry_run=False, after_uuid=None, batch_size=100)
        self.change.refresh_from_db()
        self.same.refresh_from_db()
        self.assertEqual(self.change.timezone, "America/Recife")
        self.assertEqual(self.same.timezone, "America/Manaus")
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.skipped_missing, 1)
        self.assertFalse(Project.objects.filter(uuid=missing_uuid).exists())

    def test_dry_run_does_not_write(self):
        rows = [{"uuid": str(self.change.uuid), "timezone": "America/Recife"}]
        result = sync_page(rows, project_model=Project, dry_run=True, after_uuid=None, batch_size=100)
        self.change.refresh_from_db()
        self.assertIsNone(self.change.timezone)
        self.assertEqual(result.updated, 1)

    def test_after_uuid_skips_earlier_rows(self):
        rows = [
            {"uuid": str(self.change.uuid), "timezone": "America/Recife"},
            {"uuid": str(self.keep.uuid), "timezone": "America/Fortaleza"},
        ]
        ordered = sort_results_by_uuid(rows)
        after = ordered[0]["uuid"]
        result = sync_page(
            rows,
            project_model=Project,
            dry_run=False,
            after_uuid=after,
            batch_size=100,
        )
        self.change.refresh_from_db()
        self.keep.refresh_from_db()
        self.assertEqual(result.updated, 1)
        later = ordered[1]
        later_project = Project.objects.get(uuid=later["uuid"])
        self.assertEqual(later_project.timezone, later["timezone"])
        skipped = Project.objects.get(uuid=after)
        original = "America/Sao_Paulo" if skipped.uuid == self.keep.uuid else None
        self.assertEqual(skipped.timezone, original)

    @patch("scripts.sync_project_timezones.time.sleep")
    def test_fetch_page_retries_then_succeeds(self, mock_sleep):
        client = MagicMock()
        client.get_projects_paginated.side_effect = [
            requests.RequestException("down"),
            {"results": [{"uuid": "ok"}], "next": None},
        ]
        payload = fetch_page_with_retry(client, page=1, page_size=10)
        self.assertEqual(payload["results"][0]["uuid"], "ok")
        mock_sleep.assert_called_once()
