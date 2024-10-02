from uuid import uuid4
from typing import Dict
from django.test import TestCase

import requests

from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
from nexus.task_managers.file_database.file_database import FileResponseDTO
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.projects.models import Project
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.usecases.projects.tests.project_factory import ProjectFactory

from router.entities import ProjectDTO
from router.repositories.orm import ProjectORMRepository


class BedrockFileDatabaseTestCase(TestCase):
    def setUp(self) -> None:
        self.bedrock = BedrockFileDatabase()
        self.content_base_uuid = "TEST"
        self.file_uuid = str(uuid4())

    def test_add_file(self):
        with open("/tmp/test_file.txt", "w+b") as f:
            f.write("This test shouldn't run in CI, is just for development purposes".encode("utf-8"))
            f.seek(0)
            response: FileResponseDTO = self.bedrock.add_file(
                file=f,
                content_base_uuid=self.content_base_uuid,
                file_uuid=self.file_uuid,
            )
            print(f"Filename: {response.file_name}")
            self.assertEquals(response.status, 0)
            self.assertIsNone(response.err)

    def test_delete_file_and_metadata(self):
        filename = "test_file-d6a721f9-e2d4-41cc-be24-bdaee8ddaca7.txt"
        response = self.bedrock.delete_file_and_metadata(self.content_base_uuid, filename)
        self.assertIsNone(response)

    def test_start_ingestion_job(self):
        job_id = self.bedrock.start_bedrock_ingestion()
        print(f"Job ID: {job_id}")
        self.assertIsInstance(job_id, str)

    def test_get_ingestion_job_status(self):
        job_id = "5OL7KTHSWZ"
        status = "COMPLETE"
        response = self.bedrock.get_bedrock_ingestion_status(job_id)

        print(f"Status: {response}")

        self.assertIsInstance(response, str)
        self.assertEquals(response, status)

    def test_list_bedrock_ingestion(self):
        response = self.bedrock.list_bedrock_ingestion()
        print(response)
        self.assertEquals(response, [])

    def test_search_data(self):
        response = self.bedrock.search_data(
            content_base_uuid=self.content_base_uuid,
            text="Test"
        )
        print(response)
        self.assertListEqual(["status", "data"], list(response.keys()))

    def test_create_presigned_url(self):
        filename = "test_file-7d6f95ab-5143-4a58-920b-68d56c83a5be.txt"
        url = self.bedrock.create_presigned_url(filename)
        print(url)
        response = requests.get(url)
        print(response.text)
        self.assertIsInstance(url, str)
        self.assertEquals(response.status_code, 200)


class TestChangesInProjectBedrockTestCase(TestCase):
    def setUp(self) -> None:
        self.org = OrgFactory()
        self.project = self.org.projects.create(
            name="Bedrock 1",
            indexer_database=Project.BEDROCK,
            created_by=self.org.created_by
        )
        self.project2 = ProjectFactory()
        self.project_uuid = str(self.project.uuid)
        self.project_uuid2 = str(self.project2.uuid)

    def test_project_orm_repository(self):
        
        project_dto: ProjectDTO = ProjectORMRepository().get_project(self.project_uuid)

        self.assertIsInstance(project_dto, ProjectDTO)
        self.assertEquals(self.project_uuid, project_dto.uuid)
        self.assertEquals(self.project.name, project_dto.name)
        self.assertEquals(self.project.indexer_database, project_dto.indexer_database)

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
