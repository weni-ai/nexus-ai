import json
import logging
import uuid
from typing import Dict, List
from unittest import skip
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.actions.api.views import (
    FlowsViewset,
    MessagePreviewView,
    SearchFlowView,
    TemplateActionView,
)
from nexus.actions.models import Flow
from nexus.intelligences.models import (
    ContentBaseAgent,
    ContentBaseFile,
    ContentBaseLink,
    ContentBaseText,
)
from nexus.logs.models import Message as ContactMessage
from nexus.logs.models import MessageLog
from nexus.projects.models import Project
from nexus.projects.project_dto import ProjectCreationDTO
from nexus.usecases.actions.list import ListFlowsUseCase
from nexus.usecases.actions.tests.flow_factory import TemplateActionFactory
from nexus.usecases.intelligences.get_by_uuid import (
    get_default_content_base_by_project,
    get_integrated_intelligence_by_project,
)
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from router.tests.mocks import MockIndexer


class FlowsTestCase(TestCase):
    def setUp(self) -> None:
        self.contentbase = ContentBaseFactory()

    def test_model(self):
        flow = Flow.objects.create(
            uuid=uuid.uuid4(),
            flow_uuid=uuid.uuid4(),
            name="Test Flow",
            prompt="Prompt",
            content_base=self.contentbase,
        )
        self.assertIsInstance(flow, Flow)
        self.assertFalse(flow.fallback)

    def test_model_fallback(self):
        flow = Flow.objects.create(
            uuid=uuid.uuid4(),
            flow_uuid=uuid.uuid4(),
            name="Test Flow",
            prompt="Prompt",
            content_base=self.contentbase,
            fallback=True,
        )
        self.assertIsInstance(flow, Flow)
        self.assertTrue(flow.fallback)


class FlowsViewsetTestCase(TestCase):
    def setUp_project(self):
        project_dto = ProjectCreationDTO(
            uuid=str(uuid.uuid4()),
            name="Router",
            is_template=False,
            template_type_uuid=None,
            org_uuid=str(self.org.uuid),
            brain_on=True,
        )
        project_creation = ProjectsUseCase()
        return project_creation.create_project(project_dto=project_dto, user_email=self.user.email)

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = FlowsViewset.as_view({"get": "list", "post": "create", "put": "update", "delete": "destroy"})
        self.project = ProjectFactory(
            name="Router",
            brain_on=True,
        )
        self.org = self.project.org
        self.user = self.project.created_by
        self.integrated_intel = get_integrated_intelligence_by_project(self.project.uuid)
        self.intelligence = self.integrated_intel.intelligence
        self.contentbase = get_default_content_base_by_project(self.project.uuid)

        self.flow = Flow.objects.create(
            flow_uuid=str(uuid.uuid4()),
            name="Test Flow",
            prompt="Prompt",
            content_base=self.contentbase,
        )
        self.url = f"{self.project.uuid}/flows"

    def test_list(self):
        url_list = f"{self.url}/"
        request = self.factory.get(url_list)

        force_authenticate(request, user=self.user)

        response = FlowsViewset.as_view({"get": "list"})(request, project_uuid=str(self.project.uuid))
        response.render()

        self.assertEqual(response.status_code, 200)

    def test_retrieve(self):
        flow_uuid = str(self.flow.uuid)
        url_retrieve = f"{self.url}/{flow_uuid}/"
        request = self.factory.get(url_retrieve)

        force_authenticate(request, user=self.user)

        response = FlowsViewset.as_view({"get": "retrieve"})(
            request,
            flow_uuid=flow_uuid,
            project_uuid=str(self.project.uuid),
        )
        self.assertEqual(response.status_code, 200)

    def test_update(self):
        action_uuid = str(self.flow.uuid)
        url_update = f"{self.url}/{action_uuid}/"

        prompt_update = "Update prompt"

        data = {"prompt": prompt_update}
        request = self.factory.patch(url_update, data=data)
        force_authenticate(request, user=self.user)

        response = FlowsViewset.as_view({"patch": "update"})(
            request,
            data,
            flow_uuid=action_uuid,
            project_uuid=str(self.project.uuid),
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("prompt"), prompt_update)

    def test_delete(self):
        flow_uuid = str(self.flow.uuid)
        url_delete = f"{self.url}/{flow_uuid}/"

        request = self.factory.delete(url_delete)
        force_authenticate(request, user=self.user)
        response = FlowsViewset.as_view({"delete": "destroy"})(
            request,
            flow_uuid=flow_uuid,
            project_uuid=str(self.project.uuid),
        )
        self.assertEqual(response.status_code, 204)

    def test_create(self):
        url_create = f"{self.url}/"
        flow_uuid = str(uuid.uuid4())
        data = {"uuid": flow_uuid, "name": "Flow 1", "prompt": "Prompt", "fallback": False, "action_type": "custom"}

        request = self.factory.post(url_create, data=data)

        force_authenticate(request, user=self.user)

        response = FlowsViewset.as_view({"post": "create"})(request, data, project_uuid=str(self.project.uuid))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data.get("flow_uuid"), flow_uuid)


@skip("Testing View")
class SearchFlowViewTestCase(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.view = SearchFlowView.as_view()

        self.org = OrgFactory()
        self.user = self.org.authorizations.first().user
        self.project_uuid = "45d9efca-2848-4be0-a218-73af48f04a4d"
        self.url = f"{self.project_uuid}/search-flows"

    def test_list(self):
        page_size = 1
        page = 2
        url_list = f"{self.url}?page_size={page_size}&page={page}"
        request = self.factory.get(url_list)

        force_authenticate(request, user=self.user)

        response = SearchFlowView.as_view()(
            request, project_uuid=str(self.project_uuid), page_size=page_size, page=page
        )

        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(content.keys()), ["count", "next", "previous", "results"])

    def test_get(self):
        flow_name = "Why"
        url_list = f"{self.url}?name={flow_name}"
        request = self.factory.get(url_list)

        force_authenticate(request, user=self.user)

        response = SearchFlowView.as_view()(request, project_uuid=str(self.project_uuid), name=flow_name)
        response.render()
        content = json.loads(response.content)
        self.assertEqual(list(content.keys()), ["count", "next", "previous", "results"])


class RestClient:
    flow_dict = {"uuid": "2c273a84-c32c-4b2b-8f9c-20fcc60b55d2", "name": "Test Menu"}

    def get_project_flows(self, project_uuid: str, name: str) -> List[Dict]:
        return [self.flow_dict]

    def list_project_flows(self, project_uuid: str, page_size: int, page: int):
        return {"count": 2, "next": "", "previous": "", "results": [self.flow_dict, self.flow_dict]}


class TestListFlowsUseCase(TestCase):
    def setUp(self) -> None:
        self.project_uuid = "45d9efca-2848-4be0-a218-73af48f04a4d"
        self.usecase = ListFlowsUseCase(RestClient())

    def test_search_flows_by_project_get_project_flows(self):
        expected_response = {
            "count": len([RestClient.flow_dict]),
            "next": None,
            "previous": None,
            "results": [RestClient.flow_dict],
        }
        data = self.usecase.search_flows_by_project(project_uuid=self.project_uuid, name="Test Menu")
        self.assertDictEqual(expected_response, data)

    def test_search_flows_by_project_list_project_flows(self):
        data = self.usecase.search_flows_by_project(project_uuid=self.project_uuid, page_size=2, page=1)
        self.assertIsInstance(data, dict)


@skip("View Testing")
class MessagePreviewTestCase(TestCase):
    def setUp_project(self):
        return Project.objects.create(
            uuid=str(uuid.uuid4()), name="Router", is_template=False, org=self.org, brain_on=True, created_by=self.user
        )

    def setUp_message(self, number_of_messages: int):
        contact_message = ContactMessage.objects.create(
            text=f"Message {number_of_messages}", contact_urn=self.contact_urn, status="F"
        )
        for i in range(number_of_messages):
            contact_message = ContactMessage.objects.create(
                text=f"Message {i}", contact_urn=self.contact_urn, status="S"
            )
            MessageLog.objects.create(
                message=contact_message,
                content_base=self.contentbase,
                project=self.project,
                llm_response=f"Response {i}",
            )

    def setUp(self):
        self.contact_urn = "82391837:telegram"
        self.factory = APIRequestFactory()
        self.view = MessagePreviewView.as_view()
        self.org = OrgFactory()
        self.user = self.org.authorizations.first().user
        self.project = self.setUp_project()
        self.integrated_intel = get_integrated_intelligence_by_project(self.project.uuid)
        self.intelligence = self.integrated_intel.intelligence
        self.contentbase = get_default_content_base_by_project(self.project.uuid)
        self.agent = ContentBaseAgent.objects.create(
            name="Doris",
            role="Vendas",
            personality="Extrovertida",
            goal="Auxiliar o cliente nas vendas",
            content_base=self.contentbase,
        )
        self.flow = Flow.objects.create(
            uuid=uuid.uuid4(),
            flow_uuid=uuid.uuid4(),
            name="Test Flow",
            prompt="Quando o usuário estiver interessado em testar o router",
            content_base=self.contentbase,
        )
        self.url = "/simulate-messages"
        self.setUp_message(5)

        self.file = ContentBaseFile.objects.create(
            file="http://test.com",
            file_name="test-b3269efc-def3-4663-a8b6-26c2b3ccc9ce.docx",
            extension_file="docx",
            content_base=self.contentbase,
            created_by=self.user,
        )
        self.link = ContentBaseLink.objects.create(
            content_base=self.contentbase,
            link="http://test.co",
            created_by=self.user,
        )
        self.text = ContentBaseText.objects.create(
            created_by=self.user,
            text="Test",
            file="http://test.com",
            content_base=self.contentbase,
        )

    @patch("nexus.actions.api.views.SentenXFileDataBase")
    def test_other(self, mock_indexer):
        mock_indexer.return_value = MockIndexer(file_uuid=str(self.file.uuid))
        url_create = f"{self.url}/"

        data = {
            "project_uuid": str(self.project.uuid),
            "text": "Test",
            "contact_urn": self.contact_urn,
        }

        request = self.factory.post(url_create, data=data)

        force_authenticate(request, user=self.user)

        response = MessagePreviewView.as_view()(request, data, project_uuid=str(self.project.uuid))

        response.render()
        content = json.loads(response.content)
        self.assertEqual(content.get("type"), "broadcast")
        self.assertEqual(content.get("fonts")[0].get("extension_file"), "docx")

    @patch("nexus.actions.api.views.SentenXFileDataBase")
    def test_other_link(self, mock_indexer):
        mock_indexer.return_value = MockIndexer(file_uuid=str(self.link.uuid))
        url_create = f"{self.url}/"

        data = {
            "project_uuid": str(self.project.uuid),
            "text": "Test",
            "contact_urn": self.contact_urn,
        }

        request = self.factory.post(url_create, data=data)

        force_authenticate(request, user=self.user)

        response = MessagePreviewView.as_view()(request, data, project_uuid=str(self.project.uuid))

        response.render()
        content = json.loads(response.content)
        self.assertEqual(content.get("type"), "broadcast")
        self.assertEqual(content.get("fonts")[0].get("created_file_name"), f".link:{self.link.link}")

    @patch("nexus.actions.api.views.SentenXFileDataBase")
    def test_other_text(self, mock_indexer):
        mock_indexer.return_value = MockIndexer(file_uuid=str(self.text.uuid))
        url_create = f"{self.url}/"

        data = {
            "project_uuid": str(self.project.uuid),
            "text": "Test",
            "contact_urn": self.contact_urn,
        }

        request = self.factory.post(url_create, data=data)

        force_authenticate(request, user=self.user)

        response = MessagePreviewView.as_view()(request, data, project_uuid=str(self.project.uuid))

        response.render()
        content = json.loads(response.content)
        self.assertEqual(content.get("type"), "broadcast")
        self.assertEqual(content.get("fonts")[0].get("created_file_name"), ".text")

    @patch("nexus.actions.api.views.SentenXFileDataBase")
    def test_classify(self, mock_indexer):
        mock_indexer.return_value = MockIndexer()

        url_create = f"{self.url}/"

        data = {
            "project_uuid": str(self.project.uuid),
            "text": "Olá, gostaria de testar o router",
            "contact_urn": self.contact_urn,
        }

        request = self.factory.post(url_create, data=data)

        force_authenticate(request, user=self.user)

        response = MessagePreviewView.as_view()(request, data, project_uuid=str(self.project.uuid))

        response.render()

        content = json.loads(response.content)

        self.assertEqual(content.get("type"), "flowstart")


class TemplateActionViewSetTestCase(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.view = TemplateActionView.as_view({"get": "list"})
        self.project = ProjectFactory(
            name="Router",
            brain_on=True,
        )
        self.template_action = TemplateActionFactory()
        self.url = f"{self.project.uuid}/flows/template-action"

    def test_get(self):
        request = self.factory.get(self.url)
        force_authenticate(request, user=self.project.created_by)
        response = TemplateActionView.as_view({"get": "list"})(
            request,
            project_uuid=str(self.project.uuid),
        )
        response.render()
        logging.getLogger(__name__).info("Response content rendered", extra={"length": len(response.content or b"")})
        self.assertEqual(response.status_code, 200)
