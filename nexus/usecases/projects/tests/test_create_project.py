import json
import amqp
from uuid import uuid4
from django.test import TestCase

from .project_factory import ProjectFactory, FeatureVersionFactory
from ..projects_use_case import ProjectsUseCase

from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.projects.create import ProjectAuthUseCase, CreateFeatureVersionUseCase, CreateIntegratedFeatureVersionUseCase
from nexus.usecases.users.tests.user_factory import UserFactory
from nexus.usecases.projects.dto import IntegratedFeatureVersionDTO
from nexus.usecases.projects.retrieve import RetrieveIntegratedFeatureVersion
from nexus.usecases.intelligences.create import create_base_brain_structure

from nexus.event_domain.recent_activity.mocks import mock_event_manager_notify

from nexus.projects.project_dto import ProjectCreationDTO
from nexus.projects.models import IntegratedFeatureVersion
from nexus.projects.consumers.integrated_feature_version import IntegratedFeatureVersionConsumer


class MockChannel:
    def basic_ack(*args, **kwargs):
        return True

    def basic_reject(*args, **kwargs):
        return False


class TestCreateProject(TestCase):

    def setUp(self) -> None:
        org = OrgFactory()
        self.user = org.created_by
        self.project_dto = ProjectCreationDTO(
            uuid=uuid4().hex,
            name="test_name",
            org_uuid=org.uuid,
            is_template=False,
            template_type_uuid=None,
            brain_on=False,
            authorizations=[]
        )

    def test_create_project(self):
        project = ProjectsUseCase(
            event_manager_notify=mock_event_manager_notify,
        ).create_project(
            project_dto=self.project_dto,
            user_email=self.user.email
        )
        self.assertEqual(project.uuid, self.project_dto.uuid)

    def test_create_brain_on_project(self):
        self.project_dto.brain_on = True
        project = ProjectsUseCase(
            event_manager_notify=mock_event_manager_notify,
        ).create_project(
            project_dto=self.project_dto,
            user_email=self.user.email
        )
        self.assertEqual(project.uuid, self.project_dto.uuid)
        self.assertTrue(project.brain_on)


class ProjectAuthUseCaseTestCase(TestCase):

    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.user_email = UserFactory().email

    def test_create_project_auth(self):
        consumer_msg = {
            'project': str(self.project.uuid),
            'role': 3,
            'user': self.user_email
        }
        project_auth = ProjectAuthUseCase().create_project_auth(
            consumer_msg
        )
        self.assertEqual(project_auth.project, self.project)
        self.assertEqual(project_auth.user.email, self.user_email)
        self.assertEqual(project_auth.role, 3)


class CreateFeatureVersionUseCaseTestCase(TestCase):

    def setUp(self) -> None:
        self.usecase = CreateFeatureVersionUseCase()

    def test_create_feature_version(self):
        consumer_msg = {
            'feature_version_uuid': uuid4().hex,
            'brain': {
                "agent": {
                    "name": "name",
                    "role": "role",
                    "personality": "personality"
                }
            }
        }

        feature_version = self.usecase.create_feature_version(
            consumer_msg=consumer_msg
        )
        self.assertTrue(feature_version)

    def test_empty_setup(self):
        consumer_msg = {
            'feature_version_uuid': uuid4().hex,
            'brain': {}
        }

        feature_version = self.usecase.create_feature_version(
            consumer_msg=consumer_msg
        )
        self.assertTrue(feature_version)

    def test_existing_feature_version(self):
        consumer_msg = {
            'feature_version_uuid': uuid4().hex,
            'brain': {
                "agent": {
                    "name": "name",
                    "role": "role",
                    "personality": "personality"
                }
            }
        }

        self.usecase.create_feature_version(
            consumer_msg=consumer_msg
        )

        with self.assertRaises(Exception):
            self.usecase.create_feature_version(
                consumer_msg=consumer_msg
            )


class IntegratedFeatureVersionTestCase(TestCase):
    def setUp(self) -> None:
        self.org = OrgFactory()
        self.project = self.org.projects.create(name="Test", created_by=self.org.created_by)
        self.integrated_intelligence = create_base_brain_structure(self.project)
        self.feature_version = FeatureVersionFactory()
        self.usecase = CreateIntegratedFeatureVersionUseCase()
        self.actions = [
            {
                "name": "teste 1",
                "description": "teste 1",
                "flow_uuid": str(uuid4())
            },
            {
                "name": "teste 2",
                "description": "teste 2",
                "flow_uuid": str(uuid4())
            }
        ]

    def test_create_integrated_feature_usecase(self):
        message = {
            "project_uuid": str(self.project.uuid),
            "feature_version_uuid": str(self.feature_version.uuid),
            "actions": self.actions
        }
        integrated_feature_version_dto = IntegratedFeatureVersionDTO(**message)
        integrated_feature_version = self.usecase.create(integrated_feature_version_dto)
        self.assertIsInstance(integrated_feature_version, IntegratedFeatureVersion)

    def test_create_integrated_feature_usecase_empty_actions(self):
        message = {
            "project_uuid": str(self.project.uuid),
            "feature_version_uuid": str(self.feature_version.uuid),
            "actions": []
        }
        integrated_feature_version_dto = IntegratedFeatureVersionDTO(**message)
        integrated_feature_version = self.usecase.create(integrated_feature_version_dto)
        self.assertIsInstance(integrated_feature_version, IntegratedFeatureVersion)

    def test_consumer(self):
        project_uuid = str(self.project.uuid)
        feature_version_uuid = str(self.feature_version.uuid)

        message = {
            "project_uuid": project_uuid,
            "feature_version_uuid": feature_version_uuid,
            "actions": self.actions
        }

        message = json.dumps(message)
        self.message = amqp.Message(
            body=message.encode(),
            channel=MockChannel(),
            delivery_tag="",
        )
        IntegratedFeatureVersionConsumer().consume(self.message)
        integrated_feature_version = RetrieveIntegratedFeatureVersion().get(
            project_uuid=project_uuid,
            feature_version_uuid=feature_version_uuid
        )
        self.assertIsInstance(integrated_feature_version, IntegratedFeatureVersion)
