from django.test import TestCase

from unittest.mock import patch

from nexus.usecases.projects.create import CreateIntegratedFeatureUseCase
from nexus.usecases.projects.update import ProjectUpdateUseCase, UpdateIntegratedFeatureUseCase
from nexus.usecases.projects.dto import UpdateProjectDTO, IntegratedFeatureFlowDTO

from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory
from nexus.usecases.projects.tests.project_factory import IntegratedFeatureFactory, ProjectFactory
from nexus.usecases.actions.tests.flow_factory import FlowFactory


class UpdateProjectTestCase(TestCase):

    def setUp(self) -> None:
        integrated_intelligence = IntegratedIntelligenceFactory()
        self.project = integrated_intelligence.project
        self.user = self.project.created_by
        self.uuid = self.project.uuid

    @patch("nexus.usecases.projects.update.update_message")
    def test_update_brain_on(self, mock_update_message):

        mock_update_message.return_value = None

        brain_on = True
        dto = UpdateProjectDTO(
            user_email=self.user.email,
            uuid=self.uuid,
            brain_on=brain_on
        )
        usecase = ProjectUpdateUseCase()
        updated_project = usecase.update_project(dto)
        self.assertEqual(updated_project.brain_on, brain_on)


class UpdateIntegratedFeatureTestCase(TestCase):

    def setUp(self) -> None:
        self.integrated_feature = IntegratedFeatureFactory()
        self.related_flow = FlowFactory(
            name=self.integrated_feature.current_version_setup['name'],
            prompt=self.integrated_feature.current_version_setup['prompt'],
        )
        self.project = ProjectFactory()
        self.usecase = UpdateIntegratedFeatureUseCase()
        self.project = self.integrated_feature.project

    def test_update(self):
        root_flow_uuid = self.integrated_feature.current_version_setup['root_flow_uuid']
        name = "new name"
        prompt = "new prompt"

        consumer_msg = {
            'project_uuid': str(self.project.uuid),
            'feature_uuid': self.integrated_feature.feature_uuid,
            'action': {
                'base_uuid': root_flow_uuid,
                'name': name,
                'prompt': prompt
            }
        }

        integrated_feature = self.usecase.update_integrated_feature(consumer_msg)

        self.assertEqual(integrated_feature.current_version_setup['name'], name)
        self.assertEqual(integrated_feature.current_version_setup['prompt'], prompt)

    def test_update_integrated_flow(self):
        root_flow_uuid = self.integrated_feature.current_version_setup['root_flow_uuid']
        name = "new name"
        prompt = "new prompt"

        consumer_msg = {
            'project_uuid': str(self.project.uuid),
            'feature_uuid': self.integrated_feature.feature_uuid,
            'action': {
                'root_flow_uuid': root_flow_uuid,
                'name': name,
                'prompt': prompt
            }
        }

        updated_feature = self.usecase.update_integrated_feature(consumer_msg)
        print("====================================")
        print("updated_feature: ", updated_feature.__dict__)

        update_flow_consumer_msg = {
            'project_uuid': str(self.project.uuid),
            'feature_uuid': updated_feature.feature_uuid,
            'flows': [
                {
                    'base_uuid': root_flow_uuid,
                    'new_uuid': self.related_flow.uuid
                }
            ]
        }

        flow_dto = IntegratedFeatureFlowDTO(
            project_uuid=str(self.project.uuid),
            feature_uuid=updated_feature.feature_uuid,
            flows=update_flow_consumer_msg['flows']
        )

        update_flow_usecase = CreateIntegratedFeatureUseCase()
        returned_flow = update_flow_usecase.integrate_feature_flows(
            integrated_feature_flow_dto=flow_dto
        )

        self.assertEqual(returned_flow.name, name)
