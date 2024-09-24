from uuid import uuid4
from django.test import TestCase

from .project_factory import ProjectFactory, IntegratedFeatureFactory
from ..projects_use_case import ProjectsUseCase
from nexus.event_domain.recent_activity.mocks import mock_event_manager_notify

from nexus.projects.project_dto import ProjectCreationDTO
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.projects.retrieve import get_integrated_feature
from nexus.usecases.projects.dto import IntegratedFeatureFlowDTO
from nexus.usecases.projects.create import ProjectAuthUseCase, CreateIntegratedFeatureUseCase
from nexus.usecases.users.tests.user_factory import UserFactory
from nexus.usecases.actions.tests.flow_factory import TemplateActionFactory


from nexus.actions.models import Flow


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


class IntegratedFeatureUseCaseTestCase(TestCase):

    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.usecase = CreateIntegratedFeatureUseCase()
        self.template_action = TemplateActionFactory()

    def create_integrated_feature(self):
        root_flow_uuid = uuid4().hex
        feature_uuid = uuid4().hex
        consumer_msg = {
            'project_uuid': str(self.project.uuid),
            'feature_uuid': feature_uuid,
            "action": {
                "name": "Human handoff",
                "prompt": "aaaaa",
                "root_flow_uuid": root_flow_uuid,
                "type": ""
            }
        }
        feature = self.usecase.create_integrated_feature(
            consumer_msg
        )

        self.assertEqual(feature.project, self.project)
        self.assertEqual(feature.feature_uuid, feature_uuid)
        self.assertEqual(feature.current_version_setup['root_flow_uuid'], root_flow_uuid)
        self.assertEqual(feature.current_version_setup['name'], "Human handoff")
        self.assertEqual(feature.current_version_setup['prompt'], "Whenever an user wants to talk to a human")
        self.assertFalse(feature.is_integrated)

    def create_integrated_feature_with_action_template(self):
        root_flow_uuid = uuid4().hex
        feature_uuid = uuid4().hex
        consumer_msg = {
            'project_uuid': str(self.project.uuid),
            'feature_uuid': feature_uuid,
            "action": {
                "name": "Human handoff",
                "prompt": "aaaaa",
                "root_flow_uuid": root_flow_uuid,
                "type": self.template_action.uuid
            }
        }
        feature = self.usecase.create_integrated_feature(
            consumer_msg
        )

        self.assertEqual(feature.project, self.project)
        self.assertEqual(feature.feature_uuid, feature_uuid)
        self.assertEqual(feature.current_version_setup['root_flow_uuid'], root_flow_uuid)
        self.assertEqual(feature.current_version_setup['name'], "Human handoff")
        self.assertEqual(feature.current_version_setup['prompt'], "aaaaa")
        self.assertFalse(feature.is_integrated)


class CreateIntegratedFeatureFlowsTestCase(TestCase):

    def setUp(self) -> None:
        self.integrated_feature = IntegratedFeatureFactory()
        self.project = self.integrated_feature.project
        self.usecase = CreateIntegratedFeatureUseCase()
        self.template_action = TemplateActionFactory()

    def test_integrate_flow(self):
        root_flow_uuid = self.integrated_feature.current_version_setup['root_flow_uuid']
        consumer_msg = {
            'project_uuid': str(self.project.uuid),
            'feature_uuid': self.integrated_feature.feature_uuid,
            'flows': [
                {
                    'base_uuid': root_flow_uuid,
                    'uuid': uuid4().hex,
                    'name': 'Example flow'
                }
            ]
        }
        flow_dto = IntegratedFeatureFlowDTO(
            project_uuid=str(self.project.uuid),
            feature_uuid=self.integrated_feature.feature_uuid,
            flows=consumer_msg['flows']
        )

        returned_flow = self.usecase.integrate_feature_flows(
            integrated_feature_flow_dto=flow_dto
        )

        integrated_feature = get_integrated_feature(
            project_uuid=str(self.project.uuid),
            feature_uuid=self.integrated_feature.feature_uuid
        )

        self.assertIsInstance(returned_flow, Flow)
        self.assertTrue(integrated_feature.is_integrated)

    def test_integrate_multiple_flows(self):
        root_flow_uuid = self.integrated_feature.current_version_setup['root_flow_uuid']
        consumer_msg = {
            'project_uuid': str(self.project.uuid),
            'feature_uuid': self.integrated_feature.feature_uuid,
            'flows': [
                {
                    'base_uuid': uuid4().hex,
                    'uuid': uuid4().hex,
                    'name': 'Example flow 2'
                },
                {
                    'base_uuid': root_flow_uuid,
                    'uuid': uuid4().hex,
                    'name': 'Example flow'
                },
                {
                    'base_uuid': uuid4().hex,
                    'uuid': uuid4().hex,
                    'name': 'Example flow 3'
                }
            ]
        }
        flow_dto = IntegratedFeatureFlowDTO(
            project_uuid=str(self.project.uuid),
            feature_uuid=self.integrated_feature.feature_uuid,
            flows=consumer_msg['flows']
        )
        returned_flow = self.usecase.integrate_feature_flows(
            integrated_feature_flow_dto=flow_dto
        )

        integrated_feature = get_integrated_feature(
            project_uuid=str(self.project.uuid),
            feature_uuid=self.integrated_feature.feature_uuid
        )

        self.assertIsInstance(returned_flow, Flow)
        self.assertTrue(integrated_feature.is_integrated)

    def test_integrate_flow_without_root_flow(self):
        consumer_msg = {
            'project_uuid': str(self.project.uuid),
            'feature_uuid': self.integrated_feature.feature_uuid,
            'flows': [
                {
                    'base_uuid': uuid4().hex,
                    'uuid': uuid4().hex,
                    'name': 'Example flow'
                }
            ]
        }
        flow_dto = IntegratedFeatureFlowDTO(
            project_uuid=str(self.project.uuid),
            feature_uuid=self.integrated_feature.feature_uuid,
            flows=consumer_msg['flows']
        )
        with self.assertRaises(ValueError):
            self.usecase.integrate_feature_flows(
                integrated_feature_flow_dto=flow_dto
            )

        integrated_feature = get_integrated_feature(
            project_uuid=str(self.project.uuid),
            feature_uuid=self.integrated_feature.feature_uuid
        )
        self.assertFalse(integrated_feature.is_integrated)

    def test_create_integrated_flow_template(self):
        integrated_feature_template = IntegratedFeatureFactory(
            current_version_setup={
                "name": "Human handoff",
                "root_flow_uuid": uuid4().hex,
                "prompt": "Whenever an user wants to talk to a human",
                "type": self.template_action.uuid
            }
        )
        template_action_project = integrated_feature_template.project
        consumer_msg = {
            'project_uuid': str(template_action_project.uuid),
            'feature_uuid': integrated_feature_template.feature_uuid,
            'flows': [
                {
                    'base_uuid': uuid4().hex,
                    'uuid': uuid4().hex,
                    'name': 'Example flow'
                }
            ]
        }
        flow_dto = IntegratedFeatureFlowDTO(
            project_uuid=str(self.project.uuid),
            feature_uuid=self.integrated_feature.feature_uuid,
            flows=consumer_msg['flows']
        )
        with self.assertRaises(ValueError):
            self.usecase.integrate_feature_flows(
                integrated_feature_flow_dto=flow_dto
            )

        integrated_feature = get_integrated_feature(
            project_uuid=str(self.project.uuid),
            feature_uuid=self.integrated_feature.feature_uuid
        )
        self.assertFalse(integrated_feature.is_integrated)
