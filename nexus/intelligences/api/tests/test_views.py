import json
from unittest import skip, mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from rest_framework.test import (
    APIRequestFactory,
    APITestCase,
    force_authenticate
)

from nexus.task_managers.models import ContentBaseLinkTaskManager, TaskManager

from ..views import (
    IntelligencesViewset,
    ContentBaseViewset,
    ContentBaseTextViewset,
    ContentBaseLinkViewset,
    SentenxIndexerUpdateFile,
    ContentBasePersonalizationViewSet,
    RouterRetailViewSet
)

from nexus.usecases.intelligences.tests.intelligence_factory import (
    IntelligenceFactory,
    IntegratedIntelligenceFactory,
    ContentBaseFactory,
    ContentBaseTextFactory,
    ContentBaseLinkFactory,
)
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.intelligences.tests.mocks import MockFileDataBase
from nexus.usecases.intelligences.create import create_base_brain_structure
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.agents.models import Team

from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission


@skip("View Testing")
class TestIntelligencesViewset(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = IntelligencesViewset.as_view({
            'get': 'list',
            'post': 'create',
            'put': 'update',
            'delete': 'destroy',
        })
        self.intelligence = IntelligenceFactory()
        self.user = self.intelligence.created_by
        self.org = self.intelligence.org
        self.url = f'{self.org.uuid}/intelligences/project'

    def test_get_queryset(self):

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.user)

        response = self.view(
            request,
            org_uuid=str(self.org.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_retrieve(self):

        url_retrieve = f'{self.url}/{self.intelligence.uuid}/'

        request = self.factory.get(url_retrieve)
        force_authenticate(request, user=self.user)

        response = IntelligencesViewset.as_view({'get': 'retrieve'})(
            request,
            org_uuid=str(self.org.uuid),
            pk=str(self.intelligence.uuid),
        )
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {
            'name': 'intelligence_name',
            'description': 'intelligence_description',
            'language': 'es'
        }
        request = self.factory.post(self.url, data)
        force_authenticate(request, user=self.user)

        response = self.view(
            request,
            org_uuid=str(self.org.uuid),
        )
        self.assertEqual(response.status_code, 201)

    def test_update(self):

        url_put = f'{self.url}/{self.intelligence.uuid}/'
        data = {
            'name': 'intelligence_name',
            'description': 'intelligence_description',
            'pk': str(self.intelligence.uuid),
        }
        request = self.factory.put(
            url_put,
            json.dumps(data),
            content_type='application/json'
        )
        force_authenticate(request, user=self.user)
        response = self.view(request, pk=str(self.intelligence.uuid))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], data['name'])

    def test_delete(self):
        url_delete = f'{self.url}/{self.intelligence.uuid}/'
        data = {
            'pk': str(self.intelligence.uuid),
        }

        request = self.factory.delete(
            url_delete,
            json.dumps(data),
            content_type='application/json'
        )
        force_authenticate(request, user=self.user)

        response = self.view(request, pk=str(self.intelligence.uuid))
        self.assertEqual(response.status_code, 204)


@skip("View Testing")
class TestContentBaseViewset(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = ContentBaseViewset.as_view({
            'get': 'list',
            'post': 'create',
            'put': 'update',
            'delete': 'destroy'
        })
        self.contentbase = ContentBaseFactory()
        self.user = self.contentbase.created_by
        self.intelligence = self.contentbase.intelligence

        self.url = f'{self.intelligence.uuid}/content-bases'

    def test_get_queryset(self):

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.user)
        response = self.view(
            request,
            intelligence_uuid=str(self.intelligence.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_retrieve(self):

        url_retrieve = f'{self.url}/{self.contentbase.uuid}/'
        request = self.factory.get(url_retrieve)
        force_authenticate(request, user=self.user)
        response = ContentBaseViewset.as_view({'get': 'retrieve'})(
            request,
            intelligence_uuid=str(self.intelligence.uuid),
            contentbase_uuid=str(self.contentbase.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {
            'title': 'title',
            'description': 'description',
            'language': 'pt-br'
        }
        request = self.factory.post(self.url, data)
        force_authenticate(request, user=self.user)
        response = self.view(
            request,
            intelligence_uuid=str(self.intelligence.uuid),
        )
        self.assertEqual(response.status_code, 201)

    def test_update(self):
        data = {
            'title': 'title',
            'description': 'description',
            'language': 'pt-br'
        }
        url_put = f'{self.url}/{self.contentbase.uuid}/'
        request = self.factory.put(
            url_put,
            json.dumps(data),
            content_type='application/json'
        )
        force_authenticate(request, user=self.user)
        response = self.view(
            request,
            intelligence_uuid=str(self.intelligence.uuid),
            contentbase_uuid=str(self.contentbase.uuid)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], data['title'])

    def test_delete(self):
        data = {
            'contentbase_uuid': str(self.contentbase.uuid),
        }
        url_delete = f'{self.url}/{self.contentbase.uuid}/'
        request = self.factory.delete(
            url_delete,
            json.dumps(data),
            content_type='application/json'
        )
        force_authenticate(request, user=self.user)
        response = self.view(
            request,
            intelligence_uuid=str(self.intelligence.uuid),
            contentbase_uuid=str(self.contentbase.uuid),
        )
        self.assertEqual(response.status_code, 204)


class TestContentBaseTextViewset(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = ContentBaseTextViewset.as_view({
            'get': 'list',
            'post': 'create',
            'put': 'update',
            'delete': 'destroy'
        })
        self.org = OrgFactory()
        self.user = self.org.created_by
        self.project = self.org.projects.create(
            name="Project",
            created_by=self.org.created_by
        )
        self.project.authorizations.create(user=self.user, role=3)
        self.integrated_intelligence = create_base_brain_structure(self.project)
        self.intelligence = self.integrated_intelligence.intelligence
        self.content_base = get_default_content_base_by_project(str(self.project.uuid))
        self.contentbasetext = self.__create_content_base_text(self.content_base)
        self.url = f'{self.content_base.uuid}/content-bases-text'

    def __create_content_base_text(self, content_base):
        contentbasetext = ContentBaseTextFactory()
        contentbasetext.content_base = content_base
        contentbasetext.save()
        contentbasetext.refresh_from_db()
        return contentbasetext

    def test_get_queryset(self):

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.user)
        response = self.view(
            request,
            content_base_uuid=str(self.content_base.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_retrieve(self):

        url_retrieve = f'{self.url}/{self.contentbasetext.uuid}/'
        request = self.factory.get(url_retrieve)
        force_authenticate(request, user=self.user)
        response = ContentBaseTextViewset.as_view({'get': 'retrieve'})(
            request,
            contentbase_uuid=str(self.content_base.uuid),
            contentbasetext_uuid=str(self.contentbasetext.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {
            'text': 'text',
            'intelligence_uuid': str(self.intelligence.uuid),
        }
        request = self.factory.post(self.url, data)
        force_authenticate(request, user=self.user)
        response = self.view(
            request,
            content_base_uuid=str(self.content_base.uuid)
        )
        self.assertEqual(response.status_code, 201)

    @mock.patch("nexus.usecases.intelligences.delete.DeleteContentBaseTextUseCase.delete_content_base_text_from_index")
    @mock.patch("nexus.intelligences.api.views.SentenXFileDataBase")
    def test_update(self, mock_file_database, _):
        mock_file_database = MockFileDataBase
        mock_file_database()
        text = ""
        data = {
            'text': text,
        }
        url_put = f'{self.url}/{self.contentbasetext.uuid}/'
        request = self.factory.put(
            url_put,
            json.dumps(data),
            content_type='application/json'
        )
        force_authenticate(request, user=self.user)
        response = self.view(
            request,
            content_base_uuid=str(self.content_base.uuid),
            contentbasetext_uuid=str(self.contentbasetext.uuid)
        )
        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.get("text"), text)

    @mock.patch("nexus.usecases.intelligences.delete.DeleteContentBaseTextUseCase.delete_content_base_text_from_index")
    @mock.patch("nexus.intelligences.api.views.SentenXFileDataBase")
    def test_update_empty_text(self, mock_file_database, _):
        mock_file_database = MockFileDataBase
        mock_file_database()
        text = ""
        data = {
            'text': text,
        }
        url_put = f'{self.url}/{self.contentbasetext.uuid}/'
        request = self.factory.put(
            url_put,
            json.dumps(data),
            content_type='application/json'
        )
        force_authenticate(request, user=self.user)
        response = self.view(
            request,
            content_base_uuid=str(self.content_base.uuid),
            contentbasetext_uuid=str(self.contentbasetext.uuid)
        )
        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.get("text"), text)


class TestContentBaseLinkViewset(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()

        self.org = OrgFactory()
        self.user = self.org.created_by
        self.project = self.org.projects.create(
            name="Project",
            created_by=self.org.created_by
        )
        self.project.authorizations.create(user=self.user, role=3)
        self.integrated_intelligence = create_base_brain_structure(self.project)
        self.intelligence = self.integrated_intelligence.intelligence
        self.content_base = get_default_content_base_by_project(str(self.project.uuid))
        self.contentbaselink = self.__create_content_base_link(self.content_base)

        self.task_uuid = ContentBaseLinkTaskManager.objects.create(
            content_base_link=self.contentbaselink,
            created_by=self.user
        )
        self.url = f'{self.content_base.uuid}/content-bases-link'

    def __create_content_base_link(self, content_base):
        contentbaselink = ContentBaseLinkFactory()
        contentbaselink.content_base = content_base
        contentbaselink.save()
        contentbaselink.refresh_from_db()
        return contentbaselink

    def sentenx_indexer_update_file(self, task_uuid: str, status: bool, file_type: str):
        data = {
            "task_uuid": task_uuid,
            "status": int(status),
            "file_type": file_type,
        }
        headers = {
            "Authorization": f"Bearer {settings.SENTENX_UPDATE_TASK_TOKEN}",
        }
        request = self.factory.patch(
            "/v1/content-base-file",
            data=json.dumps(data),
            content_type='application/json',
            headers=headers
        )
        response = SentenxIndexerUpdateFile.as_view()(
            request
        )
        self.assertEqual(response.status_code, 200)

    def test_list(self):
        url_retrieve = f'{self.url}'
        request = self.factory.get(url_retrieve)

        force_authenticate(request, user=self.user)

        response = ContentBaseLinkViewset.as_view({'get': 'list'})(
            request,
            content_base_uuid=str(self.content_base.uuid),
            contentbaselink_uuid=str(self.contentbaselink.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_retrieve(self):
        url_retrieve = f'{self.url}/{self.contentbaselink.uuid}/'
        request = self.factory.get(url_retrieve)

        force_authenticate(request, user=self.user)

        response = ContentBaseLinkViewset.as_view({'get': 'retrieve'})(
            request,
            content_base_uuid=str(self.content_base.uuid),
            contentbaselink_uuid=str(self.contentbaselink.uuid)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("status"), TaskManager.STATUS_WAITING)

    def test_create(self):
        data = {
            'link': 'https://example.com/',
        }
        request = self.factory.post(self.url, data)

        force_authenticate(request, user=self.user)

        response = ContentBaseLinkViewset.as_view({'post': 'create'})(
            request,
            content_base_uuid=str(self.content_base.uuid)
        )
        obj_uuid = response.data.get("uuid")
        content_base_task_manager = ContentBaseLinkTaskManager.objects.get(content_base_link__uuid=obj_uuid)

        self.sentenx_indexer_update_file(
            task_uuid=str(content_base_task_manager.uuid),
            status=True,
            file_type="link"
        )
        self.assertEqual(response.status_code, 201)

        content_base_task_manager = ContentBaseLinkTaskManager.objects.get(content_base_link__uuid=obj_uuid)
        self.assertEqual(content_base_task_manager.status, TaskManager.STATUS_SUCCESS)


class TestContentBasePersonalizationViewSet(TestCase):

    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.content_base = ContentBaseFactory(is_router=True)
        self.instruction_1 = self.content_base.instructions.first()
        self.org = self.content_base.intelligence.org
        self.user = self.org.created_by
        self.project = ProjectFactory(
            brain_on=True,
            name=self.content_base.intelligence.name,
            org=self.org,
            created_by=self.user
        )
        IntegratedIntelligenceFactory(
            intelligence=self.content_base.intelligence,
            project=self.project,
            created_by=self.user
        )
        # Create a team with human support data
        self.team = Team.objects.create(
            project=self.project,
            external_id="test-supervisor-id",
            human_support=True,
            human_support_prompt="Test human support prompt"
        )
        self.url = f'{self.project.uuid}/customization'

    def test_get_personalization(self):
        url_retrieve = f'{self.url}/'
        request = self.factory.get(url_retrieve)

        force_authenticate(request, user=self.user)

        response = ContentBasePersonalizationViewSet.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, 200)

        response.render()
        content = json.loads(response.content)

        self.assertIn('team', content)
        team_data = content['team']
        self.assertIsNotNone(team_data)
        self.assertEqual(team_data['human_support'], True)
        self.assertEqual(team_data['human_support_prompt'], "Test human support prompt")

    def test_get_personalization_without_team(self):

        # Delete existing team
        Team.objects.all().delete()

        url_retrieve = f'{self.url}/'
        request = self.factory.get(url_retrieve)

        force_authenticate(request, user=self.user)

        response = ContentBasePersonalizationViewSet.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, 200)

        response.render()
        content = json.loads(response.content)

        # Validate team data is null when no team exists
        self.assertIn('team', content)
        self.assertIsNone(content['team'])

    def test_get_personalization_external_token(self):
        url_retrieve = f'{self.url}/'
        headers = {"Authorization": f"Bearer {settings.WENIGPT_FLOWS_SEARCH_TOKEN}"}

        request = self.factory.get(url_retrieve, headers=headers)
        response = ContentBasePersonalizationViewSet.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )
        self.assertEqual(response.status_code, 200)

        # Validate team data in response
        response.render()
        content = json.loads(response.content)
        self.assertIn('team', content)
        team_data = content['team']
        self.assertIsNotNone(team_data)
        self.assertEqual(team_data['human_support'], True)
        self.assertEqual(team_data['human_support_prompt'], "Test human support prompt")

    def test_update_personalization(self):
        url_update = f'{self.url}/'

        data = {
            "agent": {
                "name": "Doris Update",
                "role": "Sales",
                "personality": "Creative",
                "goal": "Sell"
            },
            "instructions": [
                {
                    "id": self.instruction_1.id,
                    "instruction": "Be friendly"
                }
            ]
        }
        request = self.factory.put(url_update, data=data, format='json')
        force_authenticate(request, user=self.user)

        response = ContentBasePersonalizationViewSet.as_view({'put': 'update'})(
            request,
            data,
            project_uuid=str(self.project.uuid),
            format='json',
        )
        self.assertEqual(response.status_code, 200)

    def test_delete_personalization(self):
        url_update = f'{self.url}/?id={self.instruction_1.id}'
        request = self.factory.delete(url_update, format='json')
        force_authenticate(request, user=self.user)

        response = ContentBasePersonalizationViewSet.as_view({'delete': 'destroy'})(
            request,
            project_uuid=str(self.project.uuid),
            format='json',
        )
        self.assertEqual(response.status_code, 200)


class TestRetailRouterViewset(APITestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.ii = IntegratedIntelligenceFactory()
        self.user = self.ii.created_by
        self.project = self.ii.project
        self.url = reverse('project-commerce-router', kwargs={'project_uuid': str(self.project.uuid)})
        self.view = RouterRetailViewSet.as_view()

        content_type = ContentType.objects.get_for_model(self.user)
        permission, created = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            name="can communicate internally",
            content_type=content_type,
        )
        self.user.user_permissions.add(permission)

    @mock.patch('django.conf.settings.DEFAULT_RETAIL_INSTRUCTIONS', ['Try to use emojis', 'Dont change the subject'])
    def test_list(self):

        data = {
            "agent": {
                "name": "test",
                "role": "Doubt analyst",
                "personality": "Friendly",
                "goal": "Answer user questions"
            },
            "links": [
                "https://www.example.org/",
                "https://www.example2.com/",
                "https://www.example3.com.br/"
            ]
        }

        request = self.factory.post(self.url, data=data, format='json')
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=str(self.project.uuid))
        response.render()

        self.assertEqual(response.status_code, 200)

        response_json = json.loads(response.content)

        instructions = response_json.get('personalization').get('instructions')

        self.assertEqual(len(instructions), 2)
        self.assertEqual(instructions[0]['instruction'], 'Try to use emojis')
        self.assertEqual(instructions[1]['instruction'], 'Dont change the subject')

    @mock.patch('django.conf.settings.DEFAULT_RETAIL_INSTRUCTIONS', ['Try to use emojis', 'Dont change the subject'])
    def test_without_links(self):

        data = {
            "agent": {
                "name": "test",
                "role": "Doubt analyst",
                "personality": "Friendly",
                "goal": "Answer user questions"
            }
        }

        request = self.factory.post(self.url, data=data, format='json')
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=str(self.project.uuid))
        response.render()

        self.assertEqual(response.status_code, 200)

        response_json = json.loads(response.content)
        instructions = response_json.get('personalization').get('instructions')

        self.assertEqual(len(instructions), 2)
        self.assertEqual(response_json.get('links'), None)
