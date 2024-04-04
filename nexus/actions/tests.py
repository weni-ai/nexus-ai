import uuid

from django.test import TestCase
from nexus.actions.models import Flow

from rest_framework.test import APIRequestFactory
from rest_framework.test import force_authenticate

from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory

from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from nexus.projects.project_dto import ProjectCreationDTO

from nexus.actions.api.views import (
    FlowsViewset
)

from nexus.usecases.intelligences.get_by_uuid import (
    get_integretade_intelligence_by_project,
    get_default_content_base_by_project,
)


class FlowsTestCase(TestCase):
    def setUp(self) -> None:
        self.contentbase = ContentBaseFactory()

    def test_model(self):
        flow = Flow.objects.create(
            uuid=uuid.uuid4(),
            name="Test Flow",
            prompt="Prompt",
            content_base=self.contentbase,
        )
        self.assertIsInstance(flow, Flow)
        self.assertFalse(flow.fallback)

    def test_model_fallback(self):
        flow = Flow.objects.create(
            uuid=uuid.uuid4(),
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
        self.view = FlowsViewset.as_view({
            'get': 'list',
            'post': 'create',
            'put': 'update',
            'delete': 'destroy'
        })

        self.org = OrgFactory()
        self.user = self.org.authorizations.first().user
        self.project = self.setUp_project()
        self.integrated_intel = get_integretade_intelligence_by_project(self.project.uuid)
        self.intelligence = self.integrated_intel.intelligence
        self.contentbase = get_default_content_base_by_project(self.project.uuid)

        self.flow = Flow.objects.create(
            uuid=uuid.uuid4(),
            name="Test Flow",
            prompt="Prompt",
            content_base=self.contentbase,
        )
        self.url = f'{self.project.uuid}/flows'

    def test_list(self):
        url_list = f'{self.url}/'
        request = self.factory.get(url_list)

        force_authenticate(request, user=self.user)

        response = FlowsViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_retrieve(self):
        flow_uuid = str(self.flow.uuid)
        url_retrieve = f'{self.url}/{flow_uuid}/'
        request = self.factory.get(url_retrieve)

        force_authenticate(request, user=self.user)

        response = FlowsViewset.as_view({'get': 'retrieve'})(
            request,
            flow_uuid=flow_uuid,
            project_uuid=str(self.project.uuid),
        )
        self.assertEqual(response.status_code, 200)

    def test_update(self):
        flow_uuid = str(self.flow.uuid)
        url_update = f'{self.url}/{flow_uuid}/'

        prompt_update = "Update prompt"

        data = {'prompt': prompt_update}
        request = self.factory.patch(url_update, data=data)
        force_authenticate(request, user=self.user)

        response = FlowsViewset.as_view({'patch': 'update'})(
            request,
            data,
            flow_uuid=flow_uuid,
            project_uuid=str(self.project.uuid),
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("prompt"), prompt_update)

    def test_delete(self):
        flow_uuid = str(self.flow.uuid)
        url_delete = f'{self.url}/{flow_uuid}/'

        request = self.factory.delete(url_delete)
        force_authenticate(request, user=self.user)
        response = FlowsViewset.as_view({'delete': 'destroy'})(
            request,
            flow_uuid=flow_uuid,
            project_uuid=str(self.project.uuid),
        )
        self.assertEqual(response.status_code, 204)

    def test_create(self):
        url_create = f'{self.url}/'
        flow_uuid = str(uuid.uuid4())
        data = {
            "uuid": flow_uuid,
            "name": "Flow 1",
            "prompt": "Prompt",
            "fallback": False,
        }

        request = self.factory.post(url_create, data=data)

        force_authenticate(request, user=self.user)

        response = FlowsViewset.as_view({'post': 'create'})(
            request,
            data,
            project_uuid=str(self.project.uuid)
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data.get("uuid"), flow_uuid)
