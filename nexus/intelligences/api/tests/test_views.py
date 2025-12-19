import json
from unittest import mock, skip

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from freezegun import freeze_time
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory, APITestCase, force_authenticate

from nexus.agents.models import Team
from nexus.task_managers.models import ContentBaseLinkTaskManager, TaskManager
from nexus.usecases.intelligences.create import create_base_brain_structure
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.usecases.intelligences.tests.intelligence_factory import (
    ContentBaseFactory,
    ContentBaseLinkFactory,
    ContentBaseTextFactory,
    ConversationFactory,
    IntegratedIntelligenceFactory,
    IntelligenceFactory,
    LLMFactory,
    SubTopicsFactory,
    TopicsFactory,
)
from nexus.usecases.intelligences.tests.mocks import MockFileDataBase
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.users.models import User

from ..views import (
    ContentBaseLinkViewset,
    ContentBasePersonalizationViewSet,
    ContentBaseTextViewset,
    ContentBaseViewset,
    IntelligencesViewset,
    RouterRetailViewSet,
    SentenxIndexerUpdateFile,
    SubTopicsViewSet,
    TopicsViewSet,
)


@skip("View Testing")
class TestIntelligencesViewset(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = IntelligencesViewset.as_view(
            {
                "get": "list",
                "post": "create",
                "put": "update",
                "delete": "destroy",
            }
        )
        self.intelligence = IntelligenceFactory()
        self.user = self.intelligence.created_by
        self.org = self.intelligence.org
        self.url = f"{self.org.uuid}/intelligences/project"

    def test_get_queryset(self):
        request = self.factory.get(self.url)
        force_authenticate(request, user=self.user)

        response = self.view(request, org_uuid=str(self.org.uuid))
        self.assertEqual(response.status_code, 200)

    def test_retrieve(self):
        url_retrieve = f"{self.url}/{self.intelligence.uuid}/"

        request = self.factory.get(url_retrieve)
        force_authenticate(request, user=self.user)

        response = IntelligencesViewset.as_view({"get": "retrieve"})(
            request,
            org_uuid=str(self.org.uuid),
            pk=str(self.intelligence.uuid),
        )
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {"name": "intelligence_name", "description": "intelligence_description", "language": "es"}
        request = self.factory.post(self.url, data)
        force_authenticate(request, user=self.user)

        response = self.view(
            request,
            org_uuid=str(self.org.uuid),
        )
        self.assertEqual(response.status_code, 201)

    def test_update(self):
        url_put = f"{self.url}/{self.intelligence.uuid}/"
        data = {
            "name": "intelligence_name",
            "description": "intelligence_description",
            "pk": str(self.intelligence.uuid),
        }
        request = self.factory.put(url_put, json.dumps(data), content_type="application/json")
        force_authenticate(request, user=self.user)
        response = self.view(request, pk=str(self.intelligence.uuid))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], data["name"])

    def test_delete(self):
        url_delete = f"{self.url}/{self.intelligence.uuid}/"
        data = {
            "pk": str(self.intelligence.uuid),
        }

        request = self.factory.delete(url_delete, json.dumps(data), content_type="application/json")
        force_authenticate(request, user=self.user)

        response = self.view(request, pk=str(self.intelligence.uuid))
        self.assertEqual(response.status_code, 204)


@skip("View Testing")
class TestContentBaseViewset(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = ContentBaseViewset.as_view({"get": "list", "post": "create", "put": "update", "delete": "destroy"})
        self.contentbase = ContentBaseFactory()
        self.user = self.contentbase.created_by
        self.intelligence = self.contentbase.intelligence

        self.url = f"{self.intelligence.uuid}/content-bases"

    def test_get_queryset(self):
        request = self.factory.get(self.url)
        force_authenticate(request, user=self.user)
        response = self.view(request, intelligence_uuid=str(self.intelligence.uuid))
        self.assertEqual(response.status_code, 200)

    def test_retrieve(self):
        url_retrieve = f"{self.url}/{self.contentbase.uuid}/"
        request = self.factory.get(url_retrieve)
        force_authenticate(request, user=self.user)
        response = ContentBaseViewset.as_view({"get": "retrieve"})(
            request, intelligence_uuid=str(self.intelligence.uuid), contentbase_uuid=str(self.contentbase.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {"title": "title", "description": "description", "language": "pt-br"}
        request = self.factory.post(self.url, data)
        force_authenticate(request, user=self.user)
        response = self.view(
            request,
            intelligence_uuid=str(self.intelligence.uuid),
        )
        self.assertEqual(response.status_code, 201)

    def test_update(self):
        data = {"title": "title", "description": "description", "language": "pt-br"}
        url_put = f"{self.url}/{self.contentbase.uuid}/"
        request = self.factory.put(url_put, json.dumps(data), content_type="application/json")
        force_authenticate(request, user=self.user)
        response = self.view(
            request, intelligence_uuid=str(self.intelligence.uuid), contentbase_uuid=str(self.contentbase.uuid)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], data["title"])

    def test_delete(self):
        data = {
            "contentbase_uuid": str(self.contentbase.uuid),
        }
        url_delete = f"{self.url}/{self.contentbase.uuid}/"
        request = self.factory.delete(url_delete, json.dumps(data), content_type="application/json")
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
        self.view = ContentBaseTextViewset.as_view(
            {"get": "list", "post": "create", "put": "update", "delete": "destroy"}
        )
        self.org = OrgFactory()
        self.user = self.org.created_by
        self.project = self.org.projects.create(name="Project", created_by=self.org.created_by)
        self.project.authorizations.create(user=self.user, role=3)
        self.integrated_intelligence = create_base_brain_structure(self.project)
        self.intelligence = self.integrated_intelligence.intelligence
        self.content_base = get_default_content_base_by_project(str(self.project.uuid))
        self.contentbasetext = self.__create_content_base_text(self.content_base)
        self.url = f"{self.content_base.uuid}/content-bases-text"

    def __create_content_base_text(self, content_base):
        contentbasetext = ContentBaseTextFactory()
        contentbasetext.content_base = content_base
        contentbasetext.save()
        contentbasetext.refresh_from_db()
        return contentbasetext

    def test_get_queryset(self):
        request = self.factory.get(self.url)
        force_authenticate(request, user=self.user)
        response = self.view(request, content_base_uuid=str(self.content_base.uuid))
        self.assertEqual(response.status_code, 200)

    def test_retrieve(self):
        url_retrieve = f"{self.url}/{self.contentbasetext.uuid}/"
        request = self.factory.get(url_retrieve)
        force_authenticate(request, user=self.user)
        response = ContentBaseTextViewset.as_view({"get": "retrieve"})(
            request, contentbase_uuid=str(self.content_base.uuid), contentbasetext_uuid=str(self.contentbasetext.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {
            "text": "text",
            "intelligence_uuid": str(self.intelligence.uuid),
        }
        request = self.factory.post(self.url, data)
        force_authenticate(request, user=self.user)
        response = self.view(request, content_base_uuid=str(self.content_base.uuid))
        self.assertEqual(response.status_code, 201)

    @mock.patch("nexus.usecases.intelligences.delete.DeleteContentBaseTextUseCase.delete_content_base_text_from_index")
    @mock.patch("nexus.intelligences.api.views.SentenXFileDataBase")
    def test_update(self, mock_file_database, _):
        mock_file_database = MockFileDataBase
        mock_file_database()
        text = ""
        data = {
            "text": text,
        }
        url_put = f"{self.url}/{self.contentbasetext.uuid}/"
        request = self.factory.put(url_put, json.dumps(data), content_type="application/json")
        force_authenticate(request, user=self.user)
        response = self.view(
            request, content_base_uuid=str(self.content_base.uuid), contentbasetext_uuid=str(self.contentbasetext.uuid)
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
            "text": text,
        }
        url_put = f"{self.url}/{self.contentbasetext.uuid}/"
        request = self.factory.put(url_put, json.dumps(data), content_type="application/json")
        force_authenticate(request, user=self.user)
        response = self.view(
            request, content_base_uuid=str(self.content_base.uuid), contentbasetext_uuid=str(self.contentbasetext.uuid)
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
        self.project = self.org.projects.create(name="Project", created_by=self.org.created_by)
        self.project.authorizations.create(user=self.user, role=3)
        self.integrated_intelligence = create_base_brain_structure(self.project)
        self.intelligence = self.integrated_intelligence.intelligence
        self.content_base = get_default_content_base_by_project(str(self.project.uuid))
        self.contentbaselink = self.__create_content_base_link(self.content_base)

        self.task_uuid = ContentBaseLinkTaskManager.objects.create(
            content_base_link=self.contentbaselink, created_by=self.user
        )
        self.url = f"{self.content_base.uuid}/content-bases-link"

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
            "/v1/content-base-file", data=json.dumps(data), content_type="application/json", headers=headers
        )
        response = SentenxIndexerUpdateFile.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_list(self):
        url_retrieve = f"{self.url}"
        request = self.factory.get(url_retrieve)

        force_authenticate(request, user=self.user)

        response = ContentBaseLinkViewset.as_view({"get": "list"})(
            request, content_base_uuid=str(self.content_base.uuid), contentbaselink_uuid=str(self.contentbaselink.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_retrieve(self):
        url_retrieve = f"{self.url}/{self.contentbaselink.uuid}/"
        request = self.factory.get(url_retrieve)

        force_authenticate(request, user=self.user)

        response = ContentBaseLinkViewset.as_view({"get": "retrieve"})(
            request, content_base_uuid=str(self.content_base.uuid), contentbaselink_uuid=str(self.contentbaselink.uuid)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("status"), TaskManager.STATUS_WAITING)

    @mock.patch("nexus.task_managers.tasks.send_link.delay")
    def test_create(self, mock_send_link_delay):
        # Mock the send_link.delay task to run synchronously
        def mock_send_link_sync(link, user_email, content_base_link_uuid):
            from nexus.intelligences.models import ContentBaseLink
            from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase

            content_base_link = ContentBaseLink.objects.get(uuid=content_base_link_uuid)
            task_manager = CeleryTaskManagerUseCase().create_celery_link_manager(content_base_link=content_base_link)
            return {"task_uuid": task_manager.uuid}

        mock_send_link_delay.side_effect = mock_send_link_sync

        data = {
            "link": "https://example.com/",
        }
        request = self.factory.post(self.url, data)

        force_authenticate(request, user=self.user)

        response = ContentBaseLinkViewset.as_view({"post": "create"})(
            request, content_base_uuid=str(self.content_base.uuid)
        )
        obj_uuid = response.data.get("uuid")
        content_base_task_manager = ContentBaseLinkTaskManager.objects.get(content_base_link__uuid=obj_uuid)

        self.sentenx_indexer_update_file(task_uuid=str(content_base_task_manager.uuid), status=True, file_type="link")
        self.assertEqual(response.status_code, 201)

        content_base_task_manager = ContentBaseLinkTaskManager.objects.get(content_base_link__uuid=obj_uuid)
        self.assertEqual(content_base_task_manager.status, TaskManager.STATUS_SUCCESS)


class TestContentBasePersonalizationViewSet(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.content_base = ContentBaseFactory(is_router=True)

        self.org = self.content_base.intelligence.org
        self.user = self.org.created_by
        self.project = ProjectFactory(
            brain_on=True, name=self.content_base.intelligence.name, org=self.org, created_by=self.user
        )
        # Use the same intelligence as the content_base
        IntegratedIntelligenceFactory(
            intelligence=self.content_base.intelligence, project=self.project, created_by=self.user
        )

        # Get the actual content base that the view will use
        from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project

        actual_content_base = get_default_content_base_by_project(str(self.project.uuid))

        # Create instruction on the actual content base that will be used
        from nexus.intelligences.models import ContentBaseInstruction

        self.instruction_1 = ContentBaseInstruction.objects.create(
            content_base=actual_content_base, instruction="Test instruction"
        )

        # Create a team with human support data
        self.team = Team.objects.create(
            project=self.project,
            external_id="test-supervisor-id",
            human_support=True,
            human_support_prompt="Test human support prompt",
        )
        self.url = f"{self.project.uuid}/customization"

    def test_get_personalization(self):
        url_retrieve = f"{self.url}/"
        request = self.factory.get(url_retrieve)

        force_authenticate(request, user=self.user)

        response = ContentBasePersonalizationViewSet.as_view({"get": "list"})(
            request,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, 200)

        response.render()
        content = json.loads(response.content)

        self.assertIn("team", content)
        team_data = content["team"]
        self.assertIsNotNone(team_data)
        self.assertEqual(team_data["human_support"], True)
        self.assertEqual(team_data["human_support_prompt"], "Test human support prompt")

    def test_get_personalization_without_team(self):
        # Delete existing team
        Team.objects.all().delete()

        url_retrieve = f"{self.url}/"
        request = self.factory.get(url_retrieve)

        force_authenticate(request, user=self.user)

        response = ContentBasePersonalizationViewSet.as_view({"get": "list"})(
            request,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, 200)

        response.render()
        content = json.loads(response.content)

        # Validate team data contains project data when no team exists
        self.assertIn("team", content)
        team_data = content["team"]
        self.assertIsNotNone(team_data)
        # When no team exists, it should return project's human support data
        self.assertIn("human_support", team_data)
        self.assertIn("human_support_prompt", team_data)

    def test_get_personalization_external_token(self):
        url_retrieve = f"{self.url}/"
        headers = {"Authorization": f"Bearer {settings.WENIGPT_FLOWS_SEARCH_TOKEN}"}

        request = self.factory.get(url_retrieve, headers=headers)
        response = ContentBasePersonalizationViewSet.as_view({"get": "list"})(
            request,
            project_uuid=str(self.project.uuid),
        )
        self.assertEqual(response.status_code, 200)

        # Validate team data in response
        response.render()
        content = json.loads(response.content)
        self.assertIn("team", content)
        team_data = content["team"]
        self.assertIsNotNone(team_data)
        self.assertEqual(team_data["human_support"], True)
        self.assertEqual(team_data["human_support_prompt"], "Test human support prompt")

    def test_update_personalization(self):
        url_update = f"{self.url}/"

        data = {
            "agent": {"name": "Doris Update", "role": "Sales", "personality": "Creative", "goal": "Sell"},
            "instructions": [{"id": self.instruction_1.id, "instruction": "Be friendly"}],
        }
        request = self.factory.put(url_update, data=data, format="json")
        force_authenticate(request, user=self.user)

        response = ContentBasePersonalizationViewSet.as_view({"put": "update"})(
            request,
            data,
            project_uuid=str(self.project.uuid),
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_delete_personalization(self):
        url_update = f"{self.url}/?id={self.instruction_1.id}"
        request = self.factory.delete(url_update, format="json")
        force_authenticate(request, user=self.user)

        response = ContentBasePersonalizationViewSet.as_view({"delete": "destroy"})(
            request,
            project_uuid=str(self.project.uuid),
            format="json",
        )
        self.assertEqual(response.status_code, 200)


class TestRetailRouterViewset(APITestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.ii = IntegratedIntelligenceFactory()
        self.user = self.ii.created_by
        self.project = self.ii.project
        self.url = reverse("project-commerce-router", kwargs={"project_uuid": str(self.project.uuid)})
        self.view = RouterRetailViewSet.as_view()

        content_type = ContentType.objects.get_for_model(self.user)
        permission, created = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            name="can communicate internally",
            content_type=content_type,
        )
        self.user.user_permissions.add(permission)

    @mock.patch("django.conf.settings.DEFAULT_RETAIL_INSTRUCTIONS", ["Try to use emojis", "Dont change the subject"])
    @mock.patch("nexus.task_managers.tasks.send_link.delay")
    @mock.patch("nexus.task_managers.tasks_bedrock.bedrock_send_link.delay")
    def test_list(self, mock_bedrock_send_link, mock_send_link):
        data = {
            "agent": {
                "name": "test",
                "role": "Doubt analyst",
                "personality": "Friendly",
                "goal": "Answer user questions",
            },
            "links": ["https://www.example.org/", "https://www.example2.com/", "https://www.example3.com.br/"],
        }

        request = self.factory.post(self.url, data=data, format="json")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=str(self.project.uuid))
        response.render()

        self.assertEqual(response.status_code, 200)

        response_json = json.loads(response.content)

        instructions = response_json.get("personalization").get("instructions")

        self.assertEqual(len(instructions), 2)
        self.assertEqual(instructions[0]["instruction"], "Try to use emojis")
        self.assertEqual(instructions[1]["instruction"], "Dont change the subject")

    @mock.patch("django.conf.settings.DEFAULT_RETAIL_INSTRUCTIONS", ["Try to use emojis", "Dont change the subject"])
    def test_without_links(self):
        data = {
            "agent": {
                "name": "test",
                "role": "Doubt analyst",
                "personality": "Friendly",
                "goal": "Answer user questions",
            }
        }

        request = self.factory.post(self.url, data=data, format="json")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=str(self.project.uuid))
        response.render()

        self.assertEqual(response.status_code, 200)

        response_json = json.loads(response.content)
        instructions = response_json.get("personalization").get("instructions")

        self.assertEqual(len(instructions), 2)
        self.assertEqual(response_json.get("links"), None)


class TestTopicsViewSet(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = TopicsViewSet.as_view(
            {
                "get": "list",
                "post": "create",
                "put": "update",
                "delete": "destroy",
            }
        )

        self.topic = TopicsFactory()
        self.project = self.topic.project
        self.user = self.project.created_by

        self.external_token = "test-external-token"

        self.url = f"{self.project.uuid}/topics"

    def test_get_queryset_with_valid_project(self):
        request = self.factory.get(self.url)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=str(self.project.uuid))

        self.assertEqual(response.status_code, 200)

    def test_get_queryset_with_invalid_project(self):
        invalid_project_uuid = "00000000-0000-0000-0000-000000000000"
        request = self.factory.get(f"{invalid_project_uuid}/topics")
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=invalid_project_uuid)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)

    def test_list_topics(self):
        request = self.factory.get(self.url)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=str(self.project.uuid))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], self.topic.name)
        self.assertEqual(response.data[0]["uuid"], str(self.topic.uuid))
        self.assertEqual(response.data[0]["description"], self.topic.description)
        self.assertIn("subtopic", response.data[0])

    def test_retrieve_topic(self):
        url_retrieve = f"{self.url}/{self.topic.uuid}/"
        request = self.factory.get(url_retrieve)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = TopicsViewSet.as_view({"get": "retrieve"})(
                request, project_uuid=str(self.project.uuid), uuid=str(self.topic.uuid)
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], self.topic.name)
        self.assertEqual(response.data["uuid"], str(self.topic.uuid))
        self.assertEqual(response.data["description"], self.topic.description)
        self.assertIn("subtopic", response.data)

    def test_create_topic(self):
        data = {
            "name": "New Test Topic",
            "description": "Test topic description",
        }
        request = self.factory.post(self.url, data, format="json")
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=str(self.project.uuid))

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], data["name"])
        self.assertEqual(response.data["description"], data["description"])
        self.assertIn("uuid", response.data)
        self.assertIn("created_at", response.data)

    def test_create_topic_without_project_uuid(self):
        data = {
            "name": "New Test Topic",
            "description": "Test topic description",
        }
        request = self.factory.post("/invalid/topics/", data, format="json")
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=None)

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_create_topic_with_invalid_project(self):
        data = {
            "name": "New Test Topic",
            "description": "Test topic description",
        }
        invalid_project_uuid = "00000000-0000-0000-0000-000000000000"
        request = self.factory.post(f"{invalid_project_uuid}/topics/", data, format="json")
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=invalid_project_uuid)

        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.data)

    def test_update_topic(self):
        data = {
            "name": "Updated Topic Name",
            "description": "Updated topic description",
        }
        url_put = f"{self.url}/{self.topic.uuid}/"
        request = self.factory.put(url_put, json.dumps(data), content_type="application/json")
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=str(self.project.uuid), uuid=str(self.topic.uuid))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], data["name"])
        self.assertEqual(response.data["description"], data["description"])

    def test_delete_topic(self):
        url_delete = f"{self.url}/{self.topic.uuid}/"
        request = self.factory.delete(url_delete)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=str(self.project.uuid), uuid=str(self.topic.uuid))

        self.assertEqual(response.status_code, 204)

    def test_authentication_required(self):
        request = self.factory.get(self.url)

        response = self.view(request, project_uuid=str(self.project.uuid))

        self.assertEqual(response.status_code, 403)


class TestSubTopicsViewSet(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = SubTopicsViewSet.as_view(
            {
                "get": "list",
                "post": "create",
                "put": "update",
                "delete": "destroy",
            }
        )

        # Create test data
        self.subtopic = SubTopicsFactory()
        self.topic = self.subtopic.topic
        self.project = self.topic.project

        self.external_token = "test-external-token"

        self.url = f"{self.project.uuid}/topics/{self.topic.uuid}/subtopics"

    def test_get_queryset_with_valid_topic(self):
        """Test that get_queryset returns subtopics for a valid topic"""
        request = self.factory.get(self.url)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=str(self.project.uuid), topic_uuid=str(self.topic.uuid))

        self.assertEqual(response.status_code, 200)

    def test_get_queryset_with_invalid_topic(self):
        """Test that get_queryset returns empty for invalid topic"""
        invalid_topic_uuid = "00000000-0000-0000-0000-000000000000"
        request = self.factory.get(f"{self.project.uuid}/topics/{invalid_topic_uuid}/subtopics")
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=str(self.project.uuid), topic_uuid=invalid_topic_uuid)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)

    def test_list_subtopics(self):
        """Test listing subtopics for a topic"""
        request = self.factory.get(self.url)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=str(self.project.uuid), topic_uuid=str(self.topic.uuid))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], self.subtopic.name)
        self.assertEqual(response.data[0]["uuid"], str(self.subtopic.uuid))
        self.assertEqual(response.data[0]["description"], self.subtopic.description)
        self.assertEqual(str(response.data[0]["topic_uuid"]), str(self.topic.uuid))
        self.assertEqual(response.data[0]["topic_name"], self.topic.name)
        self.assertIn("topic_uuid", response.data[0])
        self.assertIn("topic_name", response.data[0])

    def test_retrieve_subtopic(self):
        """Test retrieving a specific subtopic"""
        url_retrieve = f"{self.url}/{self.subtopic.uuid}/"
        request = self.factory.get(url_retrieve)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = SubTopicsViewSet.as_view({"get": "retrieve"})(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=str(self.topic.uuid),
                uuid=str(self.subtopic.uuid),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], self.subtopic.name)
        self.assertEqual(response.data["uuid"], str(self.subtopic.uuid))
        self.assertEqual(response.data["description"], self.subtopic.description)
        self.assertEqual(str(response.data["topic_uuid"]), str(self.topic.uuid))
        self.assertEqual(response.data["topic_name"], self.topic.name)
        self.assertIn("topic_uuid", response.data)
        self.assertIn("topic_name", response.data)

    def test_create_subtopic(self):
        """Test creating a new subtopic"""
        data = {
            "name": "New Test Subtopic",
            "description": "Test subtopic description",
        }
        request = self.factory.post(self.url, data, format="json")
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=str(self.project.uuid), topic_uuid=str(self.topic.uuid))

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], data["name"])
        self.assertEqual(response.data["description"], data["description"])
        self.assertEqual(str(response.data["topic_uuid"]), str(self.topic.uuid))
        self.assertEqual(response.data["topic_name"], self.topic.name)
        self.assertIn("uuid", response.data)
        self.assertIn("created_at", response.data)

    def test_create_subtopic_without_topic_uuid(self):
        """Test creating a subtopic without topic_uuid should fail"""
        data = {
            "name": "New Test Subtopic",
            "description": "Test subtopic description",
        }
        request = self.factory.post("/invalid/subtopics/", data, format="json")
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=str(self.project.uuid), topic_uuid=None)

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_create_subtopic_with_invalid_topic(self):
        """Test creating a subtopic with invalid topic should fail"""
        data = {
            "name": "New Test Subtopic",
            "description": "Test subtopic description",
        }
        invalid_topic_uuid = "00000000-0000-0000-0000-000000000000"
        request = self.factory.post(f"{self.project.uuid}/topics/{invalid_topic_uuid}/subtopics/", data, format="json")
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=str(self.project.uuid), topic_uuid=invalid_topic_uuid)

        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.data)

    def test_update_subtopic(self):
        """Test updating a subtopic"""
        data = {
            "name": "Updated Subtopic Name",
            "description": "Updated subtopic description",
        }
        url_put = f"{self.url}/{self.subtopic.uuid}/"
        request = self.factory.put(url_put, json.dumps(data), content_type="application/json")
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=str(self.topic.uuid),
                uuid=str(self.subtopic.uuid),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], data["name"])
        self.assertEqual(response.data["description"], data["description"])

    def test_delete_subtopic(self):
        """Test deleting a subtopic"""
        url_delete = f"{self.url}/{self.subtopic.uuid}/"
        request = self.factory.delete(url_delete)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=str(self.topic.uuid),
                uuid=str(self.subtopic.uuid),
            )

        self.assertEqual(response.status_code, 204)

    def test_authentication_required(self):
        """Test that authentication is required"""
        request = self.factory.get(self.url)
        # No Authorization header

        response = self.view(request, project_uuid=str(self.project.uuid), topic_uuid=str(self.topic.uuid))

        self.assertEqual(response.status_code, 403)

    def test_subtopic_belongs_to_correct_topic(self):
        """Test that subtopics are properly associated with their topic"""
        # Create another topic
        another_topic = TopicsFactory(project=self.project)

        # Create a subtopic for the first topic
        subtopic_data = {
            "name": "Subtopic for First Topic",
            "description": "Test subtopic description",
        }
        request = self.factory.post(self.url, subtopic_data, format="json")
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = self.view(request, project_uuid=str(self.project.uuid), topic_uuid=str(self.topic.uuid))

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["description"], subtopic_data["description"])
        self.assertEqual(str(response.data["topic_uuid"]), str(self.topic.uuid))
        self.assertEqual(response.data["topic_name"], self.topic.name)

        # Verify the subtopic belongs to the correct topic
        from nexus.intelligences.models import SubTopics

        created_subtopic = SubTopics.objects.get(uuid=response.data["uuid"])
        self.assertEqual(created_subtopic.topic, self.topic)
        self.assertNotEqual(created_subtopic.topic, another_topic)

    def test_retrieve_subtopic_with_url_pattern(self):
        """Test retrieving a subtopic using the actual URL pattern (not hitting 404)"""
        url_retrieve = f"{self.url}/{self.subtopic.uuid}/"
        request = self.factory.get(url_retrieve)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            # Use the actual view with URL kwargs as they would come from the router
            response = SubTopicsViewSet.as_view({"get": "retrieve"})(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=str(self.topic.uuid),
                uuid=str(self.subtopic.uuid),
            )

        self.assertEqual(response.status_code, 200, "Retrieve should not return 404")
        self.assertEqual(response.data["name"], self.subtopic.name)
        self.assertEqual(response.data["uuid"], str(self.subtopic.uuid))
        self.assertEqual(response.data["description"], self.subtopic.description)

    def test_delete_subtopic_with_url_pattern(self):
        """Test deleting a subtopic using the actual URL pattern (not hitting 404)"""
        # Create a subtopic to delete
        subtopic_to_delete = SubTopicsFactory(topic=self.topic)
        url_delete = f"{self.url}/{subtopic_to_delete.uuid}/"
        request = self.factory.delete(url_delete)
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            # Use the actual view with URL kwargs as they would come from the router
            response = SubTopicsViewSet.as_view({"delete": "destroy"})(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=str(self.topic.uuid),
                uuid=str(subtopic_to_delete.uuid),
            )

        self.assertEqual(response.status_code, 204, "Delete should not return 404")

        # Verify the subtopic was actually deleted
        from nexus.intelligences.models import SubTopics

        self.assertFalse(
            SubTopics.objects.filter(uuid=subtopic_to_delete.uuid).exists(), "Subtopic should be deleted from database"
        )

    def test_update_subtopic_with_url_pattern(self):
        """Test updating a subtopic using the actual URL pattern (not hitting 404)"""
        data = {
            "name": "Updated Subtopic Name via URL",
            "description": "Updated subtopic description via URL",
        }
        url_put = f"{self.url}/{self.subtopic.uuid}/"
        request = self.factory.put(url_put, json.dumps(data), content_type="application/json")
        request.headers = {"Authorization": f"Bearer {self.external_token}"}

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            # Use the actual view with URL kwargs as they would come from the router
            response = SubTopicsViewSet.as_view({"put": "update"})(
                request,
                project_uuid=str(self.project.uuid),
                topic_uuid=str(self.topic.uuid),
                uuid=str(self.subtopic.uuid),
            )

        self.assertEqual(response.status_code, 200, "Update should not return 404")
        self.assertEqual(response.data["name"], data["name"])
        self.assertEqual(response.data["description"], data["description"])


@freeze_time("2025-01-23 10:00:00")
class TestSupervisorViewset(TestCase):
    def setUp(self):
        """Set up test data and client"""
        # Create test user
        self.user = User.objects.create_user(email="test@example.com", password="testpass123")

        # Create test project
        self.project = ProjectFactory(
            created_by=self.user,
        )

        # Give the user permission to access the project
        from nexus.projects.models import ProjectAuth, ProjectAuthorizationRole

        ProjectAuth.objects.update_or_create(
            user=self.user, project=self.project, defaults={"role": ProjectAuthorizationRole.MODERATOR.value}
        )

        # Create test topics
        self.topic1 = TopicsFactory(project=self.project, name="Customer Support")
        self.topic2 = TopicsFactory(project=self.project, name="Technical Issue")

        # Create test conversations
        self.conversation1 = ConversationFactory(
            project=self.project,
            topic=self.topic1,
            csat="1",  # Satisfied
            resolution="2",  # In Progress
            has_chats_room=True,
            contact_urn="whatsapp:5511999999999",
            external_id="12345",
        )

        self.conversation2 = ConversationFactory(
            project=self.project,
            topic=self.topic2,
            csat="3",  # Unsatisfied
            resolution="2",  # In Progress
            has_chats_room=False,
            contact_urn="whatsapp:5511888888888",
            external_id="67890",
        )

        # Create API client
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Base URL for supervisor endpoints
        self.base_url = reverse("supervisor", kwargs={"project_uuid": self.project.uuid})

    def _get_supervisor_list_url(self, **params):
        """Helper method to get supervisor list URL with query parameters"""
        url = self.base_url
        if params:
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            url = f"{url}?{query_string}"
        return url

    def test_list_supervisor_data_success(self):
        """Test successful listing of supervisor data"""
        start_date = "24-12-2024"
        end_date = "24-01-2025"

        url = self._get_supervisor_list_url(start_date=start_date, end_date=end_date)
        response = self.client.get(url)

        # Assertions
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check pagination structure
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("results", response.data)

        # Get the actual data from results
        results = response.data["results"]
        self.assertIsInstance(results, list)

        # Should only have conversation data now
        self.assertEqual(len(results), 2)

        # Check if conversations are returned
        conversation_urns = [item["urn"] for item in results]
        self.assertIn(self.conversation1.contact_urn, conversation_urns)
        self.assertIn(self.conversation2.contact_urn, conversation_urns)

        # Verify data format
        for item in results:
            # Check required fields
            self.assertIn("created_on", item)
            self.assertIn("urn", item)
            self.assertIn("uuid", item)
            self.assertIn("external_id", item)
            self.assertIn("csat", item)
            self.assertIn("topic", item)
            self.assertIn("has_chats_room", item)
            self.assertIn("start_date", item)
            self.assertIn("end_date", item)
            self.assertIn("resolution", item)
            self.assertIn("name", item)

            # Check resolution format (should not be tuple string)
            if item["resolution"]:
                self.assertFalse(
                    item["resolution"].startswith("("), f"Resolution should not be tuple string: {item['resolution']}"
                )

            # Check date format
            self.assertIsInstance(item["created_on"], str)
            self.assertIsInstance(item["start_date"], str)
            self.assertIsInstance(item["end_date"], str)

    def test_list_supervisor_data_with_topic_filter(self):
        """Test listing supervisor data with topic filter"""
        url = self._get_supervisor_list_url(topics="Customer Support")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["topic"], "Customer Support")

    def test_list_supervisor_data_with_csat_filter(self):
        """Test listing supervisor data with csat filter"""
        url = self._get_supervisor_list_url(csat="1")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["csat"], "1")

    def test_list_supervisor_data_with_resolution_filter(self):
        """Test listing supervisor data with resolution filter"""
        url = self._get_supervisor_list_url(resolution="2")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Both conversations should have resolution=2 (default)
        self.assertEqual(len(response.data["results"]), 2)

    def test_list_supervisor_data_with_has_chats_room_filter(self):
        """Test listing supervisor data with has_chats_room filter"""
        url = self._get_supervisor_list_url(has_chats_room="true")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertTrue(response.data["results"][0]["has_chats_room"])

    def test_list_supervisor_data_with_search_filter(self):
        """Test listing supervisor data with search filter"""
        url = self._get_supervisor_list_url(search="5511999999999")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIn("5511999999999", response.data["results"][0]["urn"])

    def test_list_supervisor_data_with_nps_filter(self):
        """Test listing supervisor data with nps filter"""
        # Set NPS for one conversation
        self.conversation1.nps = 5
        self.conversation1.save()

        url = self._get_supervisor_list_url(nps="5")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["nps"], 5)

    def test_list_supervisor_data_with_multiple_filters(self):
        """Test listing supervisor data with multiple filters"""
        url = self._get_supervisor_list_url(topics="Customer Support", has_chats_room="true", csat="1")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["topic"], "Customer Support")
        self.assertTrue(response.data["results"][0]["has_chats_room"])
        self.assertEqual(response.data["results"][0]["csat"], "1")

    def test_public_supervisor_conversations_with_filters_and_contact_urn(self):
        conv = self.conversation1
        if not conv.channel_uuid:
            import uuid as _uuid

            conv.channel_uuid = _uuid.uuid4()
            conv.save(update_fields=["channel_uuid"])

        from nexus.projects.models import ProjectApiToken

        token, salt, token_hash = ProjectApiToken.generate_token_pair()
        ProjectApiToken.objects.create(
            project=self.project,
            name="api-token",
            token_hash=token_hash,
            salt=salt,
            scope="read:supervisor_conversations",
            enabled=True,
            created_by=self.user,
        )

        url = reverse("public-supervisor-conversations", kwargs={"project_uuid": str(self.project.uuid)})
        start = conv.start_date.date().isoformat()
        end = conv.end_date.date().isoformat()
        full_url = f"{url}?start={start}&end={end}&page=1"

        client = APIClient()
        response = client.get(full_url, HTTP_AUTHORIZATION=f"ApiKey {token}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertIn("results", payload)
        results = payload["results"]
        if results:
            item = results[0]
            self.assertIn("contact_urn", item)
            self.assertIn("messages", item)

    def test_list_supervisor_data_invalid_project_uuid(self):
        """Test listing supervisor data with invalid project UUID"""
        url = reverse("supervisor", kwargs={"project_uuid": "invalid-uuid"})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_list_supervisor_data_invalid_date_format(self):
        """Test listing supervisor data with invalid date format"""
        url = self._get_supervisor_list_url(
            start_date="2024-12-24",  # Wrong format, should be DD-MM-YYYY
            end_date="2025-01-24",
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_list_supervisor_data_missing_project_uuid(self):
        """Test listing supervisor data without project UUID"""
        # Use a valid UUID format but non-existent one instead of empty string
        import uuid

        fake_uuid = str(uuid.uuid4())
        url = reverse("supervisor", kwargs={"project_uuid": fake_uuid})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("detail", response.data)


class TestLLMViewset(TestCase):
    def setUp(self):
        """Set up test data for LLMViewset tests"""
        self.user = User.objects.create_user(email="test@example.com", password="testpass123")
        self.llm = LLMFactory(created_by=self.user)
        self.project = self.llm.integrated_intelligence.project

        intelligence = self.llm.integrated_intelligence.intelligence
        if not intelligence.is_router:
            intelligence.is_router = True
            intelligence.save()

        from nexus.projects.models import ProjectAuth, ProjectAuthorizationRole

        ProjectAuth.objects.update_or_create(
            user=self.user, project=self.project, defaults={"role": ProjectAuthorizationRole.MODERATOR.value}
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.base_url = f"/api/{self.project.uuid}/llm/"

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_get_llm_config_success(self, mock_has_permission):
        """Test successfully retrieving LLM config via GET"""

        def mock_permission(request, project_uuid, method):
            from nexus.projects.models import Project
            from nexus.projects.permissions import has_project_permission

            project = Project.objects.get(uuid=project_uuid)
            return has_project_permission(request.user, project, method)

        mock_has_permission.side_effect = mock_permission

        response = self.client.get(self.base_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("uuid", response.data)
        self.assertIn("model", response.data)
        self.assertIn("setup", response.data)
        self.assertIn("advanced_options", response.data)

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_get_llm_config_no_llm_exists(self, mock_has_permission):
        """Test GET when no LLM config exists for the project"""

        def mock_permission(request, project_uuid, method):
            from nexus.projects.models import Project
            from nexus.projects.permissions import has_project_permission

            project = Project.objects.get(uuid=project_uuid)
            return has_project_permission(request.user, project, method)

        mock_has_permission.side_effect = mock_permission

        from nexus.intelligences.models import LLM
        from nexus.usecases.intelligences.get_by_uuid import get_integrated_intelligence_by_project

        project_uuid = str(self.project.uuid)
        integrated_intelligence = get_integrated_intelligence_by_project(project_uuid)
        LLM.objects.filter(integrated_intelligence=integrated_intelligence).delete()

        response = self.client.get(self.base_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"uuid": None, "model": "", "setup": None, "advanced_options": None})

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_patch_llm_config_success(self, mock_has_permission):
        """Test successfully updating LLM config via PATCH"""

        def mock_permission(request, project_uuid, method):
            from nexus.projects.models import Project
            from nexus.projects.permissions import has_project_permission

            project = Project.objects.get(uuid=project_uuid)
            return has_project_permission(request.user, project, method)

        mock_has_permission.side_effect = mock_permission

        update_data = {
            "model": "gpt-3.5-turbo",
            "setup": {
                "temperature": 0.8,
                "top_p": 0.95,
                "top_k": 40,
                "max_length": 150,
            },
            "advanced_options": {
                "stream": True,
            },
        }

        response = self.client.patch(self.base_url, data=update_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["model"], update_data["model"])

    def test_patch_llm_config_authentication_required(self):
        """Test that authentication is required for PATCH"""
        unauthenticated_client = APIClient()
        update_data = {"model": "gpt-4"}
        response = unauthenticated_client.patch(self.base_url, data=update_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_get_llm_config_project_permission_required(self, mock_has_permission):
        """Test that project permission is required"""
        mock_has_permission.return_value = False

        unauthorized_user = User.objects.create_user(email="unauthorized@test.com")
        unauthorized_client = APIClient()
        unauthorized_client.force_authenticate(user=unauthorized_user)

        response = unauthorized_client.get(self.base_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_patch_llm_config_project_permission_required(self, mock_has_permission):
        """Test that project permission is required for PATCH"""
        mock_has_permission.return_value = False

        unauthorized_user = User.objects.create_user(email="unauthorized2@test.com")
        unauthorized_client = APIClient()
        unauthorized_client.force_authenticate(user=unauthorized_user)

        update_data = {"model": "gpt-4"}
        response = unauthorized_client.patch(self.base_url, data=update_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
