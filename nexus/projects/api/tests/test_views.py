import json

from django.test import TestCase
from django.urls import reverse

from unittest.mock import patch
from rest_framework.test import force_authenticate
from rest_framework.test import APIRequestFactory
from rest_framework.test import APIClient

from nexus.projects.api.views import ProjectUpdateViewset
from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.intelligences.create import create_base_brain_structure
from nexus.logs.models import Message, MessageLog


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


class MessageDetailViewSetTestCase(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.integrated_intelligence = create_base_brain_structure(self.project)
        self.content_base = self.integrated_intelligence.intelligence.contentbases.get()
        self.user = self.project.created_by

        full_chunks = [
            {
                'full_page': 'Lorem Ipsum',
                'filename': 'testfile.pdf',
                'file_uuid': '87163514-b6de-4525-b16a-bf3d50e7815c'
            }
        ]

        reflection_data = {
            "tag": "failed",
            "request_time": 10,
            "sentence_rankings": "Statement Sentence: Lorem ipsum dolor sit amet, consectetur adipiscing elit. Aliquam faucibus euismod mollis. Pellentesque imperdiet suscipit nisi, quis lobortis tellus convallis at. Supporting Evidence: Lorem ipsum dolor sit amet, consectetur adipiscing elit. Score: 10",
        }
        llm_response = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Aliquam faucibus euismod mollis. Pellentesque imperdiet suscipit nisi."
        llm_model = "wenigpt:shark-1"
        metadata = {'agent': {'goal': 'Tirar duvidas', 'name': 'Tina', 'role': 'Atendente', 'personality': 'Amigável'}, 'instructions': []}

        self.message = Message.objects.create(
            text="Text",
            contact_urn="urn",
            status="S",
        )
        self.log = MessageLog.objects.create(
            message=self.message,
            project=self.project,
            content_base=self.content_base,
            chunks_json=full_chunks,
            reflection_data=reflection_data,
            classification="other",
            llm_response=llm_response,
            llm_model=llm_model,
            metadata=metadata
        )

    def test_view(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse(
            "message-detail",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "message_uuid": str(self.message.uuid)
            }
        )

        response = client.get(url, format='json')
        response.render()
        content = json.loads(response.content)

        self.assertIsNotNone(content.get("groundedness"))

    def test_view_permissions(self):
        from nexus.usecases.users.tests.user_factory import UserFactory

        user_401 = UserFactory()

        client = APIClient()
        client.force_authenticate(user=user_401)

        url = reverse(
            "message-detail",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "message_uuid": str(self.message.uuid)
            }
        )

        response = client.get(url, format='json')
        self.assertEquals(403, response.status_code)
