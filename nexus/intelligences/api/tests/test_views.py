import json
from unittest import skip, mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from rest_framework.test import (
    APIRequestFactory,
    APITestCase,
    force_authenticate,
    APIClient
)

from nexus.task_managers.models import ContentBaseLinkTaskManager, TaskManager

from ..views import (
    IntelligencesViewset,
    ContentBaseViewset,
    ContentBaseTextViewset,
    ContentBaseLinkViewset,
    SentenxIndexerUpdateFile,
    ContentBasePersonalizationViewSet,
    RouterRetailViewSet,
    TopicsViewSet,
    SubTopicsViewSet
)

from nexus.usecases.intelligences.tests.intelligence_factory import (
    IntelligenceFactory,
    IntegratedIntelligenceFactory,
    ContentBaseFactory,
    ContentBaseTextFactory,
    ContentBaseLinkFactory,
    TopicsFactory,
    SubTopicsFactory,
    ConversationFactory
)
from nexus.intelligences.api.tests.mocks import MockBillingRESTClient, MockBillingRESTClientMultiPage
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.intelligences.tests.mocks import MockFileDataBase
from nexus.usecases.intelligences.create import create_base_brain_structure
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.agents.models import Team

from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission
from nexus.users.models import User

from rest_framework import status
from unittest.mock import patch
from freezegun import freeze_time


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


class TestTopicsViewSet(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = TopicsViewSet.as_view({
            'get': 'list',
            'post': 'create',
            'put': 'update',
            'delete': 'destroy',
        })

        self.topic = TopicsFactory()
        self.project = self.topic.project
        self.user = self.project.created_by

        self.external_token = "test-external-token"

        self.url = f'{self.project.uuid}/topics'

    def test_get_queryset_with_valid_project(self):
        request = self.factory.get(self.url)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid)
            )

        self.assertEqual(response.status_code, 200)

    def test_get_queryset_with_invalid_project(self):
        invalid_project_uuid = "00000000-0000-0000-0000-000000000000"
        request = self.factory.get(f'{invalid_project_uuid}/topics')
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=invalid_project_uuid
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)

    def test_list_topics(self):
        request = self.factory.get(self.url)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid)
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], self.topic.name)
        self.assertEqual(response.data[0]['uuid'], str(self.topic.uuid))
        self.assertEqual(response.data[0]['description'], self.topic.description)
        self.assertIn('subtopic', response.data[0])

    def test_retrieve_topic(self):
        url_retrieve = f'{self.url}/{self.topic.uuid}/'
        request = self.factory.get(url_retrieve)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = TopicsViewSet.as_view({'get': 'retrieve'})(
                request,
                project_uuid=str(self.project.uuid),
                uuid=str(self.topic.uuid)
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], self.topic.name)
        self.assertEqual(response.data['uuid'], str(self.topic.uuid))
        self.assertEqual(response.data['description'], self.topic.description)
        self.assertIn('subtopic', response.data)

    def test_create_topic(self):
        data = {
            'name': 'New Test Topic',
            'description': 'Test topic description',
        }
        request = self.factory.post(self.url, data, format='json')
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid)
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['name'], data['name'])
        self.assertEqual(response.data['description'], data['description'])
        self.assertIn('uuid', response.data)
        self.assertIn('created_at', response.data)

    def test_create_topic_without_project_uuid(self):
        data = {
            'name': 'New Test Topic',
            'description': 'Test topic description',
        }
        request = self.factory.post('/invalid/topics/', data, format='json')
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=None
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.data)

    def test_create_topic_with_invalid_project(self):
        data = {
            'name': 'New Test Topic',
            'description': 'Test topic description',
        }
        invalid_project_uuid = "00000000-0000-0000-0000-000000000000"
        request = self.factory.post(f'{invalid_project_uuid}/topics/', data, format='json')
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=invalid_project_uuid
            )

        self.assertEqual(response.status_code, 404)
        self.assertIn('error', response.data)

    def test_update_topic(self):
        data = {
            'name': 'Updated Topic Name',
            'description': 'Updated topic description',
        }
        url_put = f'{self.url}/{self.topic.uuid}/'
        request = self.factory.put(
            url_put,
            json.dumps(data),
            content_type='application/json'
        )
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid),
                uuid=str(self.topic.uuid)
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], data['name'])
        self.assertEqual(response.data['description'], data['description'])

    def test_delete_topic(self):
        url_delete = f'{self.url}/{self.topic.uuid}/'
        request = self.factory.delete(url_delete)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid),
                uuid=str(self.topic.uuid)
            )

        self.assertEqual(response.status_code, 204)

    def test_authentication_required(self):
        request = self.factory.get(self.url)

        response = self.view(
            request,
            project_uuid=str(self.project.uuid)
        )

        self.assertEqual(response.status_code, 403)


class TestSubTopicsViewSet(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = SubTopicsViewSet.as_view({
            'get': 'list',
            'post': 'create',
            'put': 'update',
            'delete': 'destroy',
        })

        # Create test data
        self.subtopic = SubTopicsFactory()
        self.topic = self.subtopic.topic
        self.project = self.topic.project

        self.external_token = "test-external-token"

        self.url = f'{self.project.uuid}/topics/{self.topic.uuid}/subtopics'

    def test_get_queryset_with_valid_topic(self):
        """Test that get_queryset returns subtopics for a valid topic"""
        request = self.factory.get(self.url)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=str(self.topic.uuid)
            )

        self.assertEqual(response.status_code, 200)

    def test_get_queryset_with_invalid_topic(self):
        """Test that get_queryset returns empty for invalid topic"""
        invalid_topic_uuid = "00000000-0000-0000-0000-000000000000"
        request = self.factory.get(f'{self.project.uuid}/topics/{invalid_topic_uuid}/subtopics')
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=invalid_topic_uuid
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)

    def test_list_subtopics(self):
        """Test listing subtopics for a topic"""
        request = self.factory.get(self.url)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=str(self.topic.uuid)
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], self.subtopic.name)
        self.assertEqual(response.data[0]['uuid'], str(self.subtopic.uuid))
        self.assertEqual(response.data[0]['description'], self.subtopic.description)
        self.assertEqual(str(response.data[0]['topic_uuid']), str(self.topic.uuid))
        self.assertEqual(response.data[0]['topic_name'], self.topic.name)
        self.assertIn('topic_uuid', response.data[0])
        self.assertIn('topic_name', response.data[0])

    def test_retrieve_subtopic(self):
        """Test retrieving a specific subtopic"""
        url_retrieve = f'{self.url}/{self.subtopic.uuid}/'
        request = self.factory.get(url_retrieve)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = SubTopicsViewSet.as_view({'get': 'retrieve'})(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=str(self.topic.uuid),
                uuid=str(self.subtopic.uuid)
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], self.subtopic.name)
        self.assertEqual(response.data['uuid'], str(self.subtopic.uuid))
        self.assertEqual(response.data['description'], self.subtopic.description)
        self.assertEqual(str(response.data['topic_uuid']), str(self.topic.uuid))
        self.assertEqual(response.data['topic_name'], self.topic.name)
        self.assertIn('topic_uuid', response.data)
        self.assertIn('topic_name', response.data)

    def test_create_subtopic(self):
        """Test creating a new subtopic"""
        data = {
            'name': 'New Test Subtopic',
            'description': 'Test subtopic description',
        }
        request = self.factory.post(self.url, data, format='json')
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=str(self.topic.uuid)
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['name'], data['name'])
        self.assertEqual(response.data['description'], data['description'])
        self.assertEqual(str(response.data['topic_uuid']), str(self.topic.uuid))
        self.assertEqual(response.data['topic_name'], self.topic.name)
        self.assertIn('uuid', response.data)
        self.assertIn('created_at', response.data)

    def test_create_subtopic_without_topic_uuid(self):
        """Test creating a subtopic without topic_uuid should fail"""
        data = {
            'name': 'New Test Subtopic',
            'description': 'Test subtopic description',
        }
        request = self.factory.post('/invalid/subtopics/', data, format='json')
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=None
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.data)

    def test_create_subtopic_with_invalid_topic(self):
        """Test creating a subtopic with invalid topic should fail"""
        data = {
            'name': 'New Test Subtopic',
            'description': 'Test subtopic description',
        }
        invalid_topic_uuid = "00000000-0000-0000-0000-000000000000"
        request = self.factory.post(f'{self.project.uuid}/topics/{invalid_topic_uuid}/subtopics/', data, format='json')
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=invalid_topic_uuid
            )

        self.assertEqual(response.status_code, 404)
        self.assertIn('error', response.data)

    def test_update_subtopic(self):
        """Test updating a subtopic"""
        data = {
            'name': 'Updated Subtopic Name',
            'description': 'Updated subtopic description',
        }
        url_put = f'{self.url}/{self.subtopic.uuid}/'
        request = self.factory.put(
            url_put,
            json.dumps(data),
            content_type='application/json'
        )
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=str(self.topic.uuid),
                uuid=str(self.subtopic.uuid)
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], data['name'])
        self.assertEqual(response.data['description'], data['description'])

    def test_delete_subtopic(self):
        """Test deleting a subtopic"""
        url_delete = f'{self.url}/{self.subtopic.uuid}/'
        request = self.factory.delete(url_delete)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=str(self.topic.uuid),
                uuid=str(self.subtopic.uuid)
            )

        self.assertEqual(response.status_code, 204)

    def test_authentication_required(self):
        """Test that authentication is required"""
        request = self.factory.get(self.url)
        # No Authorization header

        response = self.view(
            request,
            project_uuid=str(self.project.uuid),
            topic_uuid=str(self.topic.uuid)
        )

        self.assertEqual(response.status_code, 403)

    def test_subtopic_belongs_to_correct_topic(self):
        """Test that subtopics are properly associated with their topic"""
        # Create another topic
        another_topic = TopicsFactory(project=self.project)

        # Create a subtopic for the first topic
        subtopic_data = {
            'name': 'Subtopic for First Topic',
            'description': 'Test subtopic description',
        }
        request = self.factory.post(self.url, subtopic_data, format='json')
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch('django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS', [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=str(self.topic.uuid)
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['description'], subtopic_data['description'])
        self.assertEqual(str(response.data['topic_uuid']), str(self.topic.uuid))
        self.assertEqual(response.data['topic_name'], self.topic.name)

        # Verify the subtopic belongs to the correct topic
        from nexus.intelligences.models import SubTopics
        created_subtopic = SubTopics.objects.get(uuid=response.data['uuid'])
        self.assertEqual(created_subtopic.topic, self.topic)
        self.assertNotEqual(created_subtopic.topic, another_topic)


@freeze_time("2025-01-23 10:00:00")
class TestSupervisorViewset(TestCase):

    def setUp(self):
        """Set up test data and client"""
        # Create test user
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

        # Create test project
        self.project = ProjectFactory(
            created_by=self.user,
        )

        # Create test topics
        self.topic1 = TopicsFactory(project=self.project, name="Customer Support")
        self.topic2 = TopicsFactory(project=self.project, name="Technical Issue")

        # Create test conversations
        self.conversation1 = ConversationFactory(
            project=self.project,
            topic=self.topic1,
            csat="1",  # Satisfied
            has_chats_room=True,
            contact_urn="whatsapp:5511999999999",
            external_id="12345"
        )

        self.conversation2 = ConversationFactory(
            project=self.project,
            topic=self.topic2,
            csat="3",  # Unsatisfied
            has_chats_room=False,
            contact_urn="whatsapp:5511888888888",
            external_id="67890"
        )

        # Create API client
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Mock billing client
        self.mock_billing_client = MockBillingRESTClient()

        # Base URL for supervisor endpoints
        self.base_url = reverse('supervisor', kwargs={'project_uuid': self.project.uuid})

    def _get_supervisor_list_url(self, **params):
        """Helper method to get supervisor list URL with query parameters"""
        url = self.base_url
        if params:
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            url = f"{url}?{query_string}"
        return url

    @patch('nexus.usecases.intelligences.supervisor.BillingRESTClient')
    def test_list_supervisor_data_success(self, mock_billing_client_class):
        """Test successful listing of supervisor data"""
        # Configure mock
        mock_billing_client_class.return_value = self.mock_billing_client

        start_date = "2024-12-24"
        end_date = "2025-01-24"

        url = self._get_supervisor_list_url(
            start_date=start_date,
            end_date=end_date
        )
        response = self.client.get(url)

        # Assertions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check pagination structure
        self.assertIn('count', response.data)
        self.assertIn('next', response.data)
        self.assertIn('previous', response.data)
        self.assertIn('results', response.data)
        
        # Get the actual data from results
        results = response.data['results']
        self.assertIsInstance(results, list)

        conversation_data = [item for item in results if not item['is_billing_only']]
        billing_data = [item for item in results if item['is_billing_only']]

        self.assertEqual(len(conversation_data), 2)
        self.assertGreater(len(billing_data), 0)

        # Check if conversations are returned
        conversation_urns = [item['urn'] for item in conversation_data]
        self.assertIn(self.conversation1.contact_urn, conversation_urns)
        self.assertIn(self.conversation2.contact_urn, conversation_urns)

        # Check if billing data is returned
        billing_urns = [item['urn'] for item in billing_data]
        self.assertIn("whatsapp:5511999999999", billing_urns)

        # Verify data format
        for item in results:
            # Check required fields
            self.assertIn('created_on', item)
            self.assertIn('urn', item)
            self.assertIn('uuid', item)
            self.assertIn('external_id', item)
            self.assertIn('csat', item)
            self.assertIn('topic', item)
            self.assertIn('has_chats_room', item)
            self.assertIn('start_date', item)
            self.assertIn('end_date', item)
            self.assertIn('resolution', item)
            self.assertIn('is_billing_only', item)

            # Check resolution format (should not be tuple string)
            if item['resolution']:
                self.assertFalse(
                    item['resolution'].startswith('('), 
                    f"Resolution should not be tuple string: {item['resolution']}"
                )

            # Check date format
            self.assertIsInstance(item['created_on'], str)
            self.assertIsInstance(item['start_date'], str)
            self.assertIsInstance(item['end_date'], str)

    @patch('nexus.usecases.intelligences.supervisor.BillingRESTClient')
    def test_list_supervisor_data_with_topic_filter(self, mock_billing_client_class):
        """Test listing supervisor data with topic filter"""
        # Configure mock
        mock_billing_client_class.return_value = self.mock_billing_client

        """Test listing supervisor data with topic filter"""
        url = self._get_supervisor_list_url(topic="Customer")
        response = self.client.get(url)



        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['topic'], "Customer Support")

    @patch('nexus.usecases.intelligences.supervisor.BillingRESTClient')
    def test_list_supervisor_data_with_csat_filter(self, mock_billing_client_class):
        """Test listing supervisor data with csat filter"""
        # Configure mock
        mock_billing_client_class.return_value = self.mock_billing_client

        """Test listing supervisor data with csat filter"""
        url = self._get_supervisor_list_url(csat="1")
        response = self.client.get(url)



        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['csat'], "1")

    @patch('nexus.usecases.intelligences.supervisor.BillingRESTClient')
    def test_list_supervisor_data_with_has_chats_room_filter(self, mock_billing_client_class):
        """Test listing supervisor data with has_chats_room filter"""
        # Configure mock
        mock_billing_client_class.return_value = self.mock_billing_client

        """Test listing supervisor data with has_chats_room filter"""
        url = self._get_supervisor_list_url(has_chats_room="true")
        response = self.client.get(url)



        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Expect 2 results: 1 conversation + 1 billing record with has_chats_room=True
        self.assertEqual(len(response.data['results']), 2)

        # Verify all returned items have has_chats_room=True
        for item in response.data['results']:
            self.assertTrue(item['has_chats_room'])

    @patch('nexus.usecases.intelligences.supervisor.BillingRESTClient')
    def test_list_supervisor_data_with_date_filters(self, mock_billing_client_class):
        """Test listing supervisor data with date filters"""
        # Configure mock
        mock_billing_client_class.return_value = self.mock_billing_client

        # Test with date filters - use fixed dates for deterministic testing
        start_date = "2025-01-20"  # 3 days ago
        end_date = "2025-01-23"    # today



        url = self._get_supervisor_list_url(
            start_date=start_date,
            end_date=end_date
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data['results'], list)

        # Should return conversations since they were created during test setup
        # which happens within the frozen time context
        self.assertGreater(len(response.data['results']), 0)

    def test_supervisor_data_unauthorized(self):
        """Test supervisor endpoints without authentication"""
        # Remove authentication
        self.client.force_authenticate(user=None)

        # Test list endpoint
        url = self._get_supervisor_list_url()
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('nexus.usecases.intelligences.supervisor.BillingRESTClient')
    def test_supervisor_data_invalid_project_uuid(self, mock_billing_client_class):
        """Test supervisor endpoints with invalid project UUID"""
        # Configure mock
        mock_billing_client_class.return_value = self.mock_billing_client

        import uuid
        fake_project_uuid = uuid.uuid4()

        # Test list endpoint with fake project UUID
        url = reverse('supervisor', kwargs={'project_uuid': fake_project_uuid})
        response = self.client.get(url)

        # Should return 404 for invalid project UUID
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)
        self.assertIn("not found", response.data["error"])

    @patch('nexus.usecases.intelligences.supervisor.BillingRESTClient')
    def test_pagination_with_single_page_billing_data(self, mock_billing_client_class):
        """Test pagination with single page billing data"""
        # Configure mock
        mock_billing_client_class.return_value = self.mock_billing_client

        start_date = "2024-12-24"
        end_date = "2025-01-24"

        url = self._get_supervisor_list_url(
            start_date=start_date,
            end_date=end_date,
            page_size=3
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check pagination structure
        self.assertIn('next', response.data)
        self.assertIn('previous', response.data)
        self.assertIn('results', response.data)
        self.assertIn('count', response.data)

        # Should have results (conversations + billing data)
        self.assertGreater(len(response.data['results']), 0)

        # Verify pagination links
        if response.data['next']:
            # Test next page
            next_response = self.client.get(response.data['next'])
            self.assertEqual(next_response.status_code, status.HTTP_200_OK)
            self.assertIn('results', next_response.data)

    @patch('nexus.usecases.intelligences.supervisor.BillingRESTClient')
    def test_pagination_with_multi_page_billing_data(self, mock_billing_client_class):
        """Test pagination with multi-page billing data"""
        # Configure mock with multi-page billing client
        mock_multi_page_client = MockBillingRESTClientMultiPage(total_pages=3, items_per_page=5)
        mock_billing_client_class.return_value = mock_multi_page_client

        # Test with date filters to include billing data
        start_date = "2024-12-24"
        end_date = "2025-01-24"

        url = self._get_supervisor_list_url(
            start_date=start_date,
            end_date=end_date,
            page_size=5  # Request page size to test pagination
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check pagination structure
        self.assertIn('next', response.data)
        self.assertIn('previous', response.data)
        self.assertIn('results', response.data)
        self.assertIn('count', response.data)

        # Should have results (conversations + billing data from first page)
        self.assertGreater(len(response.data['results']), 0)

        # Test pagination through all pages
        all_results = []
        current_url = url

        while current_url:
            page_response = self.client.get(current_url)
            self.assertEqual(page_response.status_code, status.HTTP_200_OK)

            page_results = page_response.data['results']
            all_results.extend(page_results)

            # Move to next page
            current_url = page_response.data.get('next')

            # Safety check to prevent infinite loop
            if len(all_results) > 50:
                break

        # Should have collected results from multiple pages
        self.assertGreater(len(all_results), 5)  # More than one page worth

        # Verify all results have required fields
        for item in all_results:
            self.assertIn('created_on', item)
            self.assertIn('urn', item)
            self.assertIn('uuid', item)
            self.assertIn('external_id', item)
            self.assertIn('csat', item)
            self.assertIn('topic', item)
            self.assertIn('has_chats_room', item)
            self.assertIn('start_date', item)
            self.assertIn('end_date', item)
            self.assertIn('resolution', item)
            self.assertIn('is_billing_only', item)

    @patch('nexus.usecases.intelligences.supervisor.BillingRESTClient')
    def test_pagination_with_filters_and_multi_page_data(self, mock_billing_client_class):
        """Test pagination with filters applied to multi-page billing data"""
        # Configure mock with multi-page billing client
        mock_multi_page_client = MockBillingRESTClientMultiPage(total_pages=3, items_per_page=5)
        mock_billing_client_class.return_value = mock_multi_page_client

        # Test with filters and date range
        start_date = "2024-12-24"
        end_date = "2025-01-24"

        url = self._get_supervisor_list_url(
            start_date=start_date,
            end_date=end_date,
            has_chats_room="true",  # Apply filter
            page_size=3  # Small page size to test pagination
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check pagination structure
        self.assertIn('next', response.data)
        self.assertIn('previous', response.data)
        self.assertIn('results', response.data)
        self.assertIn('count', response.data)

        # Test pagination with filters
        all_filtered_results = []
        current_url = url

        while current_url:
            page_response = self.client.get(current_url)
            self.assertEqual(page_response.status_code, status.HTTP_200_OK)

            page_results = page_response.data['results']
            all_filtered_results.extend(page_results)

            # Move to next page
            current_url = page_response.data.get('next')

            # Safety check to prevent infinite loop
            if len(all_filtered_results) > 30:
                break

        # Verify all results respect the filter
        for item in all_filtered_results:
            self.assertTrue(item['has_chats_room'])

    @patch('nexus.usecases.intelligences.supervisor.BillingRESTClient')
    def test_pagination_cursor_consistency(self, mock_billing_client_class):
        """Test that pagination cursors work correctly and maintain data consistency"""
        # Configure mock with multi-page billing client
        mock_multi_page_client = MockBillingRESTClientMultiPage(total_pages=2, items_per_page=3)
        mock_billing_client_class.return_value = mock_multi_page_client

        # Test with date filters
        start_date = "2024-12-24"
        end_date = "2025-01-24"

        url = self._get_supervisor_list_url(
            start_date=start_date,
            end_date=end_date,
            page_size=4  # Page size to test pagination
        )

        # Get first page
        first_page_response = self.client.get(url)
        self.assertEqual(first_page_response.status_code, status.HTTP_200_OK)

        first_page_results = first_page_response.data['results']
        first_page_next = first_page_response.data.get('next')

        # Get second page using next cursor
        if first_page_next:
            second_page_response = self.client.get(first_page_next)
            self.assertEqual(second_page_response.status_code, status.HTTP_200_OK)

            second_page_results = second_page_response.data['results']
            second_page_previous = second_page_response.data.get('previous')

            # Verify no overlap between pages
            first_page_ids = {item['external_id'] for item in first_page_results if item['external_id']}
            second_page_ids = {item['external_id'] for item in second_page_results if item['external_id']}

            # Should be no overlap in external_ids
            self.assertEqual(len(first_page_ids.intersection(second_page_ids)), 0)

            # Test previous cursor works
            if second_page_previous:
                previous_page_response = self.client.get(second_page_previous)
                self.assertEqual(previous_page_response.status_code, status.HTTP_200_OK)

                # Should get back to first page
                previous_page_results = previous_page_response.data['results']
                self.assertEqual(len(previous_page_results), len(first_page_results))

    @patch('nexus.usecases.intelligences.supervisor.BillingRESTClient')
    def test_pagination_with_conversation_and_billing_data_mapping(self, mock_billing_client_class):
        """Test pagination when billing data maps to existing conversations"""
        # Configure mock with billing data that has some matching external_ids
        mock_multi_page_client = MockBillingRESTClientMultiPage(total_pages=2, items_per_page=3)
        mock_billing_client_class.return_value = mock_multi_page_client

        # Create additional conversations with external_ids that might match billing data
        conversation3 = ConversationFactory(
            project=self.project,
            topic=self.topic1,
            csat="2",
            has_chats_room=True,
            contact_urn="whatsapp:551100000000",
            external_id="0"  # This should match billing data ID 0
        )

        conversation4 = ConversationFactory(
            project=self.project,
            topic=self.topic2,
            csat="4",
            has_chats_room=False,
            contact_urn="whatsapp:551100000001",
            external_id="1"  # This should match billing data ID 1
        )

        # Test with date filters
        start_date = "2024-12-24"
        end_date = "2025-01-24"

        url = self._get_supervisor_list_url(
            start_date=start_date,
            end_date=end_date,
            page_size=3
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data['results']

        # Get the billing external_ids from the mock
        billing_external_ids = {'0', '1', '2', '3', '4', '5'}
        conversation_external_ids = {conv.external_id for conv in [conversation3, conversation4]}

        for item in results:
            if item['external_id'] in billing_external_ids:
                # This is a billing item - check if it's enriched
                if item['external_id'] in conversation_external_ids:
                    # Should be enriched with conversation data
                    self.assertFalse(item['is_billing_only'])
                    self.assertIsNotNone(item['uuid'])
                    self.assertIsNotNone(item['topic'])
                else:
                    # Should be billing-only data
                    self.assertTrue(item['is_billing_only'])
                    self.assertIsNone(item['uuid'])
                    self.assertIsNone(item['topic'])
            else:
                # This is a conversation item (not from billing) - should always be enriched
                self.assertFalse(item['is_billing_only'])
                self.assertIsNotNone(item['uuid'])
                self.assertIsNotNone(item['topic'])

    @patch('nexus.usecases.intelligences.supervisor.BillingRESTClient')
    def test_pagination_edge_cases(self, mock_billing_client_class):
        """Test pagination edge cases including empty results and large page sizes"""
        # Configure mock with multi-page billing client
        mock_multi_page_client = MockBillingRESTClientMultiPage(total_pages=1, items_per_page=2)
        mock_billing_client_class.return_value = mock_multi_page_client

        # Test with date filters that might result in no conversations
        start_date = "2020-01-01"  # Very old date
        end_date = "2020-01-02"    # Very old date

        # Test with large page size
        url = self._get_supervisor_list_url(
            start_date=start_date,
            end_date=end_date,
            page_size=100  # Large page size
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check pagination structure even with empty results
        self.assertIn('next', response.data)
        self.assertIn('previous', response.data)
        self.assertIn('results', response.data)
        self.assertIn('count', response.data)

        # Should still have billing data even if no conversations match date range
        self.assertGreater(len(response.data['results']), 0)

        # Test with very small page size
        url_small = self._get_supervisor_list_url(
            start_date=start_date,
            end_date=end_date,
            page_size=1  # Very small page size
        )
        response_small = self.client.get(url_small)

        self.assertEqual(response_small.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(response_small.data['results']), 1)

        # Test pagination with no date filters (should still work)
        url_no_dates = self._get_supervisor_list_url(
            page_size=3
        )
        response_no_dates = self.client.get(url_no_dates)

        self.assertEqual(response_no_dates.status_code, status.HTTP_200_OK)
        self.assertIn('results', response_no_dates.data)

        # Should have conversation data even without date filters
        self.assertGreater(len(response_no_dates.data['results']), 0)
