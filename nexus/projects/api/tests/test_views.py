from django.test import TestCase

from unittest.mock import patch
from rest_framework.test import force_authenticate
from rest_framework.test import APIRequestFactory

from nexus.projects.api.views import ProjectUpdateViewset
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class TestProjectUpdateViewSet(TestCase):

    def setUp(self):
        self.project = ProjectFactory()
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
