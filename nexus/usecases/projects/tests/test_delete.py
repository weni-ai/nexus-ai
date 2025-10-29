from uuid import uuid4

from django.test import TestCase

from nexus.usecases.projects.delete import delete_integrated_feature
from nexus.usecases.projects.tests.project_factory import IntegratedFeatureFactory


class TestDeleteIntegratedFeature(TestCase):
    def setUp(self) -> None:
        self.integrated_feature = IntegratedFeatureFactory()

    def test_delete_integrated_feature(self):
        self.assertTrue(
            delete_integrated_feature(
                project_uuid=self.integrated_feature.project.uuid, feature_uuid=self.integrated_feature.feature_uuid
            )
        )

    def test_integrated_feature_does_not_exists(self):
        with self.assertRaises(ValueError):
            delete_integrated_feature(project_uuid=self.integrated_feature.project.uuid, feature_uuid=uuid4().hex)

    def test_delete_integrated_feature_exception(self):
        with self.assertRaises(Exception):
            delete_integrated_feature(project_uuid="a", feature_uuid="123")
