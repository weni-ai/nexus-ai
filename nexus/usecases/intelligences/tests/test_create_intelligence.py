from django.test import TestCase

from ..create import (
    CreateIntelligencesUseCase,
    CreateContentBaseUseCase,
    CreateContentBaseTextUseCase,
    create_integrated_intelligence,
    create_llm,
    create_base_brain_structure
)
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.intelligences.tests.intelligence_factory import (
    ContentBaseFactory,
    IntelligenceFactory,
    IntegratedIntelligenceFactory
)
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.intelligences.intelligences_dto import ContentBaseDTO, ContentBaseTextDTO, LLMDTO

from nexus.usecases.event_driven.mocks import mock_recent_activity_message


class TestListIntelligenceUseCase(TestCase):

    def setUp(self):
        self.org = OrgFactory()

    def test_create_intelligence_use_case(self):

        use_case = CreateIntelligencesUseCase(mock_recent_activity_message)
        intelligences_create = use_case.create_intelligences(
            name="name",
            description="description",
            org_uuid=self.org.uuid,
            user_email=self.org.created_by
        )
        self.assertEqual(intelligences_create.name, "name")


class TestCreateContentBaseUseCase(TestCase):

    def setUp(self):
        self.org = OrgFactory()
        self.intelligence = IntelligenceFactory(org=self.org)

    def test_create_content_base_use_case(self):
        use_case = CreateContentBaseUseCase(mock_recent_activity_message)
        content_base_create = use_case.create_contentbase(
            intelligence_uuid=self.intelligence.uuid,
            user_email=self.org.created_by,
            title="title",
            description="description",
            language='en-us'
        )
        self.assertEqual(content_base_create.title, "title")

    def test_create_content_base_text_use_case(self):
        contentbase = ContentBaseFactory()
        content_base_dto = ContentBaseDTO(
            uuid=contentbase.uuid,
            title=contentbase.title,
            intelligence_uuid=str(contentbase.intelligence.uuid),
            created_by_email=contentbase.created_by.email
        )
        content_base_text_dto = ContentBaseTextDTO(
            file="http://file.url/file.txt",
            file_name="text file",
            text="text",
            content_base_uuid=content_base_dto.uuid,
            user_email=content_base_dto.created_by_email
        )
        use_case = CreateContentBaseTextUseCase()
        content_base_text_create = use_case.create_contentbasetext(
            content_base_dto,
            content_base_text_dto
        )
        self.assertEqual(content_base_text_create.text, "text")


class TestCreateIntegratedIntelligence(TestCase):

    def setUp(self) -> None:
        self.intelligence = IntelligenceFactory()
        self.org = self.intelligence.org
        self.user = self.intelligence.created_by
        self.project = ProjectFactory(
            org=self.org,
            created_by=self.user
        )

    def test_create_integrated_intelligence(self):
        integrated_intelligence = create_integrated_intelligence(
            intelligence_uuid=self.intelligence.uuid,
            user_email=self.user.email,
            project_uuid=self.project.uuid
        )
        self.assertEqual(integrated_intelligence.intelligence.uuid, self.intelligence.uuid)
        self.assertEqual(integrated_intelligence.project.uuid, self.project.uuid)


class TestLLM(TestCase):

    def setUp(self) -> None:

        self.integrated_inteligence = IntegratedIntelligenceFactory()
        ContentBaseFactory(
            intelligence=self.integrated_inteligence.intelligence,
            created_by=self.integrated_inteligence.intelligence.created_by,
            is_router=True
        )

        setup = {
            'temperature': 0.5,
            'top_p': 0.9,
            'top_k': 0.9,
            'max_length': 100,
            'threshold': 0.5,
        }
        self.dto = LLMDTO(
            model="gpt2",
            user_email=self.integrated_inteligence.created_by.email,
            project_uuid=str(self.integrated_inteligence.project.uuid),
            setup=setup
        )

    def test_create_llm(self):
        created_llm = create_llm(self.dto)
        self.assertEqual(created_llm.model, self.dto.model)
        self.assertEqual(created_llm.setup.get('temperature'), self.dto.setup.get('temperature'))


class TestBrain(TestCase):

    def setUp(self) -> None:
        self.project = ProjectFactory()

    def test_create_brain(self):
        brain = create_base_brain_structure(self.project)
        self.assertEqual(brain.intelligence.name, self.project.name)
        self.assertEqual(brain.intelligence.org, self.project.org)
        self.assertEqual(brain.intelligence.created_by, self.project.created_by)
        self.assertEqual(brain.intelligence.contentbases.first().title, self.project.name)
        self.assertEqual(brain.intelligence.contentbases.first().created_by, self.project.created_by)
        self.assertTrue(brain.intelligence.contentbases.first().is_router)
        self.assertEqual(brain.project, self.project)
        self.assertEqual(brain.created_by, self.project.created_by)
