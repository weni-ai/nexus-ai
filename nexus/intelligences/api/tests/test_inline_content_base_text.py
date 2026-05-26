from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.intelligences.api.views import InlineContentBaseTextViewset
from nexus.intelligences.models import ContentBaseText
from nexus.usecases.intelligences.tests.intelligence_factory import (
    ContentBaseFactory,
    ContentBaseTextFactory,
    IntegratedIntelligenceFactory,
)


class InlineContentBaseTextViewsetTestCase(TestCase):
    def setUp(self):
        self.permission_patcher = patch(
            "nexus.projects.api.permissions.has_external_general_project_permission",
            return_value=True,
        )
        self.permission_patcher.start()
        self.addCleanup(self.permission_patcher.stop)

        self.factory = APIRequestFactory()
        self.integrated = IntegratedIntelligenceFactory()
        self.integrated.intelligence.is_router = True
        self.integrated.intelligence.save(update_fields=["is_router"])
        self.project = self.integrated.project
        self.user = self.integrated.created_by
        self.router_content_base = ContentBaseFactory(
            intelligence=self.integrated.intelligence,
            created_by=self.user,
            is_router=True,
        )
        self.view_list = InlineContentBaseTextViewset.as_view({"get": "list", "post": "create"})
        self.view_detail = InlineContentBaseTextViewset.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        )

    def _list(self):
        request = self.factory.get("/")
        force_authenticate(request, user=self.user)
        return self.view_list(request, project_uuid=str(self.project.uuid))

    @patch("nexus.intelligences.api.views.upload_text_file.delay")
    def test_create_and_list_ordered_by_last_updated(self, mock_upload):
        create_request = self.factory.post(
            "/",
            {"text": "First document", "title": "Doc A"},
            format="json",
        )
        force_authenticate(create_request, user=self.user)
        create_response = self.view_list(create_request, project_uuid=str(self.project.uuid))
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["title"], "Doc A")
        mock_upload.assert_called_once()

        create_request_2 = self.factory.post(
            "/",
            {"text": "Second document", "title": "Doc B"},
            format="json",
        )
        force_authenticate(create_request_2, user=self.user)
        create_response_2 = self.view_list(create_request_2, project_uuid=str(self.project.uuid))
        self.assertEqual(create_response_2.status_code, status.HTTP_201_CREATED)

        list_response = self._list()
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        results = list_response.data.get("results", list_response.data)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["title"], "Doc B")

    @patch("nexus.intelligences.api.views.upload_text_file.delay")
    def test_create_default_untitled_title(self, mock_upload):
        request = self.factory.post("/", {"text": "Body"}, format="json")
        force_authenticate(request, user=self.user)
        response = self.view_list(request, project_uuid=str(self.project.uuid))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "Untitled")

    def test_create_rejects_empty_text(self):
        request = self.factory.post("/", {"text": "   "}, format="json")
        force_authenticate(request, user=self.user)
        response = self.view_list(request, project_uuid=str(self.project.uuid))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ContentBaseText.objects.filter(content_base=self.router_content_base).count(), 0)

    @patch("nexus.intelligences.api.views.upload_text_file.delay")
    def test_retrieve_by_uuid(self, mock_upload):
        create_request = self.factory.post("/", {"text": "Retrieve me", "title": "T"}, format="json")
        force_authenticate(create_request, user=self.user)
        created = self.view_list(create_request, project_uuid=str(self.project.uuid))
        cbt_uuid = created.data["uuid"]

        retrieve_request = self.factory.get("/")
        force_authenticate(retrieve_request, user=self.user)
        response = self.view_detail(
            retrieve_request,
            project_uuid=str(self.project.uuid),
            contentbasetext_uuid=cbt_uuid,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["text"], "Retrieve me")

    @patch("nexus.intelligences.api.views.upload_text_file.delay")
    def test_patch_title_only_skips_reindex(self, mock_upload):
        text = ContentBaseTextFactory(content_base=self.router_content_base, created_by=self.user)
        mock_upload.reset_mock()

        with patch.object(InlineContentBaseTextViewset, "_reindex_inline_content_base_text") as mock_reindex:
            request = self.factory.patch("/", {"title": "Renamed"}, format="json")
            force_authenticate(request, user=self.user)
            response = self.view_detail(
                request,
                project_uuid=str(self.project.uuid),
                contentbasetext_uuid=str(text.uuid),
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["title"], "Renamed")
            mock_reindex.assert_not_called()

    def test_patch_rejects_empty_body(self):
        text = ContentBaseTextFactory(content_base=self.router_content_base, created_by=self.user)
        request = self.factory.patch("/", {}, format="json")
        force_authenticate(request, user=self.user)
        response = self.view_detail(
            request,
            project_uuid=str(self.project.uuid),
            contentbasetext_uuid=str(text.uuid),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_rejects_whitespace_text(self):
        text = ContentBaseTextFactory(content_base=self.router_content_base, created_by=self.user)
        request = self.factory.patch("/", {"text": "  "}, format="json")
        force_authenticate(request, user=self.user)
        response = self.view_detail(
            request,
            project_uuid=str(self.project.uuid),
            contentbasetext_uuid=str(text.uuid),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_rejects_whitespace_title_only(self):
        text = ContentBaseTextFactory(content_base=self.router_content_base, created_by=self.user)
        request = self.factory.patch("/", {"title": "  "}, format="json")
        force_authenticate(request, user=self.user)
        response = self.view_detail(
            request,
            project_uuid=str(self.project.uuid),
            contentbasetext_uuid=str(text.uuid),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
