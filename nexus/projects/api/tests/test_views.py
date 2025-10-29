from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.projects.api.views import ProjectUpdateViewset
from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory


class TestProjectUpdateViewSet(TestCase):
    def setUp(self):
        integrated_intelligence = IntegratedIntelligenceFactory()
        self.project = integrated_intelligence.project
        self.factory = APIRequestFactory()
        self.view = ProjectUpdateViewset.as_view()
        self.user = self.project.created_by
        self.url = f"/api/{self.project.uuid}/"

    @patch("nexus.usecases.projects.update.update_message")
    def test_update(self, mock_update_message):
        mock_update_message.return_value = None

        request = self.factory.patch(self.url, {"brain_on": True})
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project.uuid)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["brain_on"])
        self.assertTrue(mock_update_message.called)
