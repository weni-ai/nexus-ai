from django.test import TestCase

from uuid import uuid4

from nexus.usecases.projects.tests.project_factory import IntegratedFeatureFactory
from nexus.usecases.projects.delete import delete_integrated_feature
from nexus.usecases.intelligences.create import create_base_brain_structure

from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.actions.models import Flow


class TestDeleteIntegratedFeature(TestCase):

    def setUp(self) -> None:
        self.integrated_feature = IntegratedFeatureFactory()
        self.project = self.integrated_feature.project
        self.integrated_intelligence = create_base_brain_structure(self.project)
        self.content_base = get_default_content_base_by_project(str(self.project.uuid))
        actions = self.integrated_feature.current_version_setup

        self.flow_list = []
        for action in actions:
            self.flow_list.append(
                Flow.objects.create(
                    uuid=str(action.get("root_flow_uuid")),
                    name=action.get("name"),
                    prompt=action.get("prompt"),
                    content_base=self.content_base,
                )
            )

    def test_delete_integrated_feature(self):
        self.assertTrue(
            delete_integrated_feature(
                project_uuid=self.integrated_feature.project.uuid,
                feature_uuid=self.integrated_feature.feature_uuid
            )
        )
        with self.assertRaises(Flow.DoesNotExist):
            for flow in self.flow_list:
                Flow.objects.get(uuid=flow.uuid)

    def test_integrated_feature_does_not_exists(self):
        with self.assertRaises(ValueError):
            delete_integrated_feature(
                project_uuid=self.integrated_feature.project.uuid,
                feature_uuid=uuid4().hex
            )

    def test_delete_integrated_feature_exception(self):
        with self.assertRaises(Exception):
            delete_integrated_feature(
                project_uuid='a',
                feature_uuid="123"
            )
