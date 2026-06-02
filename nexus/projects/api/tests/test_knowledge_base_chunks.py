from unittest import mock

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.projects.api.views import KnowledgeBaseChunksView
from nexus.projects.models import Project
from nexus.projects.permissions import has_project_permission
from nexus.usecases.intelligences.get_by_uuid import get_or_create_default_integrated_intelligence_by_project
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class TestKnowledgeBaseChunksView(TestCase):
    def setUp(self):
        self.project = ProjectFactory()
        self.integrated_intelligence = get_or_create_default_integrated_intelligence_by_project(
            project_uuid=self.project.uuid
        )
        self.content_base = self.integrated_intelligence.intelligence.contentbases.get(is_router=True)
        self.project.indexer_database = Project.BEDROCK
        self.project.save()

        self.factory = APIRequestFactory()
        self.view = KnowledgeBaseChunksView.as_view()
        self.user = self.project.created_by
        self.project_uuid = str(self.project.uuid)
        self.url = f"/api/{self.project_uuid}/knowledge-base/chunks"

        self._patcher = mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
        self._mock_ext_permission = self._patcher.start()

        def _local_permission(request, project_uuid, method):
            try:
                project = Project.objects.get(uuid=project_uuid)
                return has_project_permission(request.user, project, method)
            except Project.DoesNotExist:
                return False

        self._mock_ext_permission.side_effect = _local_permission

    def tearDown(self):
        self._patcher.stop()

    @mock.patch("nexus.projects.api.views.list_chunks")
    def test_get_chunks_success(self, mock_list_chunks):
        mock_list_chunks.return_value = {
            "count": 2,
            "page_size": 50,
            "next_cursor": None,
            "results": [
                {
                    "id": "doc-1",
                    "text": "chunk one",
                    "filename": "file.pdf",
                    "file_uuid": "file-uuid-1",
                    "metadata": {"contentBaseUuid": str(self.content_base.uuid)},
                }
            ],
        }

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["page_size"], 50)
        self.assertIsNone(response.data["next_cursor"])
        self.assertEqual(len(response.data["results"]), 1)
        mock_list_chunks.assert_called_once_with(
            content_base_uuid=str(self.content_base.uuid),
            data_source_id=mock.ANY,
            page_size=50,
            cursor=None,
        )

    @mock.patch("nexus.projects.api.views.list_chunks")
    def test_get_chunks_with_pagination_params(self, mock_list_chunks):
        mock_list_chunks.return_value = {
            "count": 100,
            "page_size": 10,
            "next_cursor": "cursor-token",
            "results": [],
        }

        request = self.factory.get(self.url, {"page_size": "10", "cursor": "prev-cursor"})
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["next_cursor"], "cursor-token")
        mock_list_chunks.assert_called_once_with(
            content_base_uuid=str(self.content_base.uuid),
            data_source_id=mock.ANY,
            page_size=10,
            cursor="prev-cursor",
        )

    def test_get_chunks_invalid_page_size(self):
        request = self.factory.get(self.url, {"page_size": "0"})
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("page_size", response.data["error"])

    def test_get_chunks_sentenx_project_returns_400(self):
        self.project.indexer_database = Project.SENTENX
        self.project.save()

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Bedrock", response.data["error"])

    def test_get_chunks_project_not_found(self):
        missing_uuid = "00000000-0000-0000-0000-000000000099"
        self._mock_ext_permission.side_effect = lambda request, project_uuid, method: True

        request = self.factory.get(f"/api/{missing_uuid}/knowledge-base/chunks")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=missing_uuid)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_chunks_content_base_not_found(self):
        self.content_base.delete()

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @mock.patch("nexus.projects.api.views.list_chunks")
    def test_get_chunks_invalid_cursor_returns_400(self, mock_list_chunks):
        mock_list_chunks.side_effect = ValueError("Invalid cursor")

        request = self.factory.get(self.url, {"cursor": "bad-cursor"})
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Invalid cursor")

    @mock.patch("nexus.projects.api.views.list_chunks")
    def test_get_chunks_opensearch_error_returns_502(self, mock_list_chunks):
        from nexus.task_managers.file_database.opensearch_knowledge_base import OpenSearchKnowledgeBaseError

        mock_list_chunks.side_effect = OpenSearchKnowledgeBaseError("OpenSearch search failed")

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
