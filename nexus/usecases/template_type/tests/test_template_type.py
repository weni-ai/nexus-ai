from uuid import uuid4

from django.test import TestCase

from nexus.usecases.intelligences.tests.intelligence_factory import IntelligenceFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory

from ..template_type_usecase import TemplateTypeDTO, TemplateTypeUseCase
from .template_type_factory import TemplateTypeFactory


class TestTemplateTypeUseCase(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.intelligence = IntelligenceFactory(org=self.project.org)
        self.usecase = TemplateTypeUseCase()
        self.dto = TemplateTypeDTO(uuid=str(uuid4()), name="name", project_uuid=self.project.uuid)
        self.template_type = TemplateTypeFactory()

    def test_get_intelligences_info_by_project(self):
        info = self.usecase.get_intelligences_info_by_project(project=self.project)
        self.assertEqual(info["intelligences"][0]["uuid"], self.intelligence.uuid)

    def test_get_by_uuid(self):
        self.assertEqual(self.usecase.get_by_uuid(self.template_type.uuid), self.template_type)
        wrong_uuid = str(uuid4())
        with self.assertRaises(Exception):  # noqa: B017
            self.usecase.get_by_uuid(wrong_uuid)
