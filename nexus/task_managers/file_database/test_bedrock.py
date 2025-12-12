import json
from unittest import skip
from unittest.mock import patch
from uuid import uuid4

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory

from nexus.intelligences.models import ContentBaseFile, ContentBaseLink, ContentBaseText
from nexus.projects.models import Project
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
from nexus.task_managers.file_database.file_database import FileResponseDTO
from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.task_managers.models import (
    ContentBaseFileTaskManager,
    ContentBaseLinkTaskManager,
    ContentBaseTextTaskManager,
    TaskManager,
)
from nexus.task_managers.tasks_bedrock import (
    check_ingestion_job_status,
    start_ingestion_job,
)
from nexus.usecases.intelligences.create import create_base_brain_structure
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFileFactory
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase
from router.entities import ProjectDTO
from router.repositories.orm import ProjectORMRepository


@skip("Development tests for bedrock")
class BedrockFileDatabaseTestCase(TestCase):
    def setUp(self) -> None:
        self.bedrock = BedrockFileDatabase()
        self.content_base_uuid = "TEST"
        self.file_uuid = str(uuid4())

    def test_add_file(self):
        with open("/tmp/test_file.txt", "w+b") as f:
            f.write(b"This test shouldn't run in CI, is just for development purposes")
            f.seek(0)
            response: FileResponseDTO = self.bedrock.add_file(
                file=f,
                content_base_uuid=self.content_base_uuid,
                file_uuid=self.file_uuid,
            )
            import logging

            logging.getLogger(__name__).debug("Filename: %s", response.file_name)
            self.assertEqual(response.status, 0)
            self.assertIsNone(response.err)

    def test_delete_file_and_metadata(self):
        filename = "test_file-d6a721f9-e2d4-41cc-be24-bdaee8ddaca7.txt"
        response = self.bedrock.delete_file_and_metadata(self.content_base_uuid, filename)
        self.assertIsNone(response)

    def test_start_ingestion_job(self):
        job_id = self.bedrock.start_bedrock_ingestion()
        import logging

        logging.getLogger(__name__).debug("Job ID: %s", job_id)
        self.assertIsInstance(job_id, str)

    def test_get_ingestion_job_status(self):
        job_id = "JOT2LSEMHF"
        status = "COMPLETE"
        response = self.bedrock.get_bedrock_ingestion_status(job_id)

        import logging

        logging.getLogger(__name__).debug("Status: %s", response)

        self.assertIsInstance(response, str)
        self.assertEqual(response, status)

    def test_list_bedrock_ingestion(self):
        response = self.bedrock.list_bedrock_ingestion()
        import logging

        logging.getLogger(__name__).debug("Response: %s", response)
        self.assertEqual(response, [])

    def test_search_data(self):
        response = self.bedrock.search_data(content_base_uuid=self.content_base_uuid, text="Test")
        import logging

        logging.getLogger(__name__).debug("Response: %s", response)
        self.assertListEqual(["status", "data"], list(response.keys()))

    def test_create_presigned_url(self):
        filename = "test_file-7d6f95ab-5143-4a58-920b-68d56c83a5be.txt"
        url = self.bedrock.create_presigned_url(filename)
        import logging

        logging.getLogger(__name__).debug("URL: %s", url)
        response = requests.get(url)
        import logging

        logging.getLogger(__name__).debug("Response text: %s", response.text[:100])
        self.assertIsInstance(url, str)
        self.assertEqual(response.status_code, 200)


@skip("Development tests for bedrock")
class TestChangesInProjectBedrockTestCase(TestCase):
    def setUp(self) -> None:
        self.org = OrgFactory()
        self.project = self.org.projects.create(
            name="Bedrock 1", indexer_database=Project.BEDROCK, created_by=self.org.created_by
        )
        self.project2 = ProjectFactory()
        self.project_uuid = str(self.project.uuid)
        self.project_uuid2 = str(self.project2.uuid)

    def test_project_orm_repository(self):
        project_dto: ProjectDTO = ProjectORMRepository().get_project(self.project_uuid)

        self.assertIsInstance(project_dto, ProjectDTO)
        self.assertEqual(self.project_uuid, project_dto.uuid)
        self.assertEqual(self.project.name, project_dto.name)
        self.assertEqual(self.project.indexer_database, project_dto.indexer_database)

    def test_get_indexer_database(self):
        usecase = ProjectsUseCase()
        bedrock = usecase.get_indexer_database_by_uuid(self.project_uuid)
        sentenx = usecase.get_indexer_database_by_uuid(self.project_uuid2)

        self.assertIsInstance(bedrock(), BedrockFileDatabase)
        self.assertIsInstance(sentenx(), SentenXFileDataBase)

        bedrock = usecase.get_indexer_database_by_project(self.project)
        sentenx = usecase.get_indexer_database_by_project(self.project2)

        self.assertIsInstance(bedrock(), BedrockFileDatabase)
        self.assertIsInstance(sentenx(), SentenXFileDataBase)


@skip
class TestBedrockTasksTestCase(TestCase):
    def setUp(self) -> None:
        self.content_base_file = ContentBaseFileFactory()
        self.task_manager = CeleryTaskManagerUseCase().create_celery_task_manager(
            content_base_file=self.content_base_file
        )
        self.celery_task_manager_uuid = str(self.task_manager.uuid)

    def test_check_ingestion_job_status(self):
        self.assertEqual(self.task_manager.status, TaskManager.STATUS_WAITING)
        ingestion_job_id = "IRHKH8JT0J"
        file_type = "file"

        response = check_ingestion_job_status(self.celery_task_manager_uuid, ingestion_job_id, file_type=file_type)
        self.task_manager.refresh_from_db()

        self.assertTrue(response)
        self.assertEqual(self.task_manager.status, TaskManager.STATUS_SUCCESS)

    @patch("nexus.task_managers.tasks_bedrock.check_ingestion_job_status")
    def test_start_ingestion_job(self, _):
        self.assertEqual(self.task_manager.status, TaskManager.STATUS_WAITING)
        file_type = "file"

        start_ingestion_job(self.celery_task_manager_uuid, file_type=file_type)

        self.task_manager.refresh_from_db()
        import logging

        logging.getLogger(__name__).debug("Job id: %s", self.task_manager.ingestion_job_id)
        self.assertEqual(self.task_manager.status, TaskManager.STATUS_PROCESSING)


@skip("Development tests for bedrock")
class TestContentBaseBedrockTestCase(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.org = OrgFactory()
        self.project = self.org.projects.create(
            name="Bedrock 1", indexer_database=Project.BEDROCK, created_by=self.org.created_by
        )
        self.user = self.org.created_by
        self.project.authorizations.create(user=self.user, role=3)
        self.integrated_intelligence = create_base_brain_structure(self.project)
        self.content_base = get_default_content_base_by_project(str(self.project.uuid))
        self.content_base_uuid = str(self.content_base.uuid)
        self.url = f"{self.content_base.uuid}/content-bases-file/"

    def test_view_create_content_base_file(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("content-base-file-list", kwargs={"content_base_uuid": str(self.content_base.uuid)})
        file = SimpleUploadedFile("file.txt", b"Test File")

        data = {
            "file": file,
            "extension_file": "txt",
        }
        response = client.post(url, data, format="multipart")
        response.render()
        content = json.loads(response.content)

        file_uuid = content.get("uuid")

        task_manager = ContentBaseFileTaskManager.objects.get(content_base_file__uuid=file_uuid)
        self.assertEqual(response.status_code, 201)
        self.assertIn(task_manager.status, [TaskManager.STATUS_SUCCESS, TaskManager.STATUS_PROCESSING])

    def test_view_create_content_base_text(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("content-bases-text-list", kwargs={"content_base_uuid": str(self.content_base.uuid)})
        data = {"text": "Just nod if you can hear me"}
        response = client.post(url, data, format="json")
        response.render()
        content = json.loads(response.content)
        import logging

        logging.getLogger(__name__).debug("Content base uuid: %s", str(self.content_base.uuid))

        file_uuid = content.get("uuid")

        task_manager = ContentBaseTextTaskManager.objects.get(content_base_text__uuid=file_uuid)
        self.assertEqual(response.status_code, 201)
        self.assertIn(task_manager.status, [TaskManager.STATUS_SUCCESS, TaskManager.STATUS_PROCESSING])

    def test_view_create_content_base_link(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("content-base-link-list", kwargs={"content_base_uuid": str(self.content_base.uuid)})
        data = {"link": "https://docs.djangoproject.com/en/5.1/ref/request-response/#django.http.HttpRequest.FILES"}
        response = client.post(url, data, format="json")
        response.render()
        content = json.loads(response.content)
        import logging

        logging.getLogger(__name__).debug("Content base uuid: %s", str(self.content_base.uuid))

        file_uuid = content.get("uuid")

        task_manager = ContentBaseLinkTaskManager.objects.get(content_base_link__uuid=file_uuid)
        self.assertEqual(response.status_code, 201)
        self.assertIn(task_manager.status, [TaskManager.STATUS_SUCCESS, TaskManager.STATUS_PROCESSING])

    def test_view_delete_content_base_link(self):
        self.content_base.uuid = "e1c5b03b-d569-4e5d-bbed-0b0e285f15b7"
        self.content_base.save()

        client = APIClient()
        content_base_link = ContentBaseLink.objects.create(
            uuid="a47ded65-1dc4-48b3-a1cd-cb27987cfde9",
            link="https://docs.djangoproject.com/en/5.1/ref/request-response/#django.http.HttpRequest.FILES",
            content_base=self.content_base,
            name="a47ded65-1dc4-48b3-a1cd-cb27987cfde9-5113bdc7-53c9-4857-8102-9ca7baea04b6.md",
            created_by=self.user,
        )
        content_base_link_uuid = str(content_base_link.uuid)
        client.force_authenticate(user=self.user)
        url = reverse(
            "content-base-link-detail",
            kwargs={"content_base_uuid": self.content_base_uuid, "contentbaselink_uuid": content_base_link_uuid},
        )
        response = client.delete(url, format="json")
        response.render()

        with self.assertRaises(ContentBaseLinkTaskManager.DoesNotExist):
            ContentBaseLinkTaskManager.objects.get(content_base_link__uuid=content_base_link_uuid)

    def test_view_delete_content_base_text(self):
        self.content_base.uuid = "baef775e-8ed3-465f-818e-d7e67ff46ecf"
        self.content_base.save()
        text_uuid = "620ddbff-5ecb-4bbd-b771-9025ea91e8f6"
        filename = "Bedrock-1-c6023317-1d9c-4fac-a123-bab262f40852.txt"
        client = APIClient()

        content_base_text = ContentBaseText.objects.create(
            uuid=text_uuid,
            content_base=self.content_base,
            file_name=filename,
            created_by=self.user,
        )
        content_base_text_uuid = str(content_base_text.uuid)
        client.force_authenticate(user=self.user)
        url = reverse(
            "content-bases-text-detail",
            kwargs={"content_base_uuid": self.content_base_uuid, "contentbasetext_uuid": content_base_text_uuid},
        )
        response = client.delete(url, format="json")
        response.render()

        with self.assertRaises(ContentBaseTextTaskManager.DoesNotExist):
            ContentBaseTextTaskManager.objects.get(content_base_text__uuid=content_base_text_uuid)

    def test_view_delete_content_base_file(self):
        self.content_base.uuid = "1eacef76-92e2-45b4-bb1a-82fc7f373050"
        self.content_base.save()

        file_uuid = "1eacef76-92e2-45b4-bb1a-82fc7f373050"
        filename = "file-d88855c1-97e8-4f68-afaf-30e12b7dc5aa.txt"
        ext = filename.split(".")[1]

        client = APIClient()

        content_base_file = ContentBaseFile.objects.create(
            uuid=file_uuid, content_base=self.content_base, file_name=filename, created_by=self.user, extension_file=ext
        )
        content_base_file_uuid = str(content_base_file.uuid)
        client.force_authenticate(user=self.user)
        url = reverse(
            "content-base-file-detail",
            kwargs={"content_base_uuid": self.content_base_uuid, "contentbase_file_uuid": content_base_file_uuid},
        )

        response = client.delete(url, format="json")
        response.render()

        with self.assertRaises(ContentBaseFileTaskManager.DoesNotExist):
            ContentBaseFileTaskManager.objects.get(content_base_file__uuid=content_base_file_uuid)

    def test_view_update_content_base_text(self):
        self.content_base.uuid = "1b2a7752-6977-420b-937f-a935b26a199b"
        self.content_base.save()
        filename = "Bedrock-2-fef7af31-a8fa-4a47-893d-4b821466fab9.txt"

        client = APIClient()
        content_base_text = ContentBaseText.objects.create(
            file_name=filename, text="Esse é um texto", content_base=self.content_base, created_by=self.user
        )
        data = {"text": "Esse é um texto (Atualizado 1)"}

        content_base_text_uuid = str(content_base_text.uuid)
        client.force_authenticate(user=self.user)

        url = reverse(
            "content-bases-text-detail",
            kwargs={"content_base_uuid": str(self.content_base.uuid), "contentbasetext_uuid": content_base_text_uuid},
        )
        response = client.put(url, data, format="json")
        response.render()
        import logging

        logging.getLogger(__name__).debug("Response: %s", response)
