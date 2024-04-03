from django.test import TestCase

from ..list import (
    ListIntelligencesUseCase,
    ListContentBaseUseCase,
    ListContentBaseTextUseCase,
    ListAllIntelligenceContentUseCase,
    ListContentBaseFileUseCase,
    get_llm_config,
)
from .intelligence_factory import (
    IntelligenceFactory,
    ContentBaseFactory,
    ContentBaseTextFactory,
    ContentBaseFileFactory,
    LLMFactory,
)
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class TestListIntelligenceUseCase(TestCase):

    def setUp(self):
        self.org = OrgFactory()
        self.intelligence = IntelligenceFactory(org=self.org)

    def test_count_intelligence_use_case(self):
        use_case = ListIntelligencesUseCase()
        intelligences_list = use_case.get_org_intelligences(
            org_uuid=self.org.uuid,
            user_email=self.org.created_by.email
        )
        self.assertEqual(1, len(intelligences_list))


class TestListContentBaseUseCase(TestCase):

    def setUp(self):

        self.intelligence = IntelligenceFactory()
        self.contentbase = ContentBaseFactory(intelligence=self.intelligence)

    def test_count_contentbase_use_case(self):
        use_case = ListContentBaseUseCase()
        contentbase_list = use_case.get_intelligence_contentbases(
            self.intelligence.uuid,
            user_email=self.intelligence.created_by.email
        )
        self.assertEqual(1, len(contentbase_list))


class TestListContentBaseTextUseCase(TestCase):

    def setUp(self):
        self.contentbasetext = ContentBaseTextFactory()

    def test_count_contentbasetext_use_case(self):
        use_case = ListContentBaseTextUseCase()
        contentbasetext_list = use_case.get_contentbase_contentbasetexts(
            self.contentbasetext.content_base.uuid,
            user_email=self.contentbasetext.created_by.email
        )
        self.assertEqual(1, len(contentbasetext_list))


class TestListAllIntelligenceContentUseCase(TestCase):

    def setUp(self):
        self.project = ProjectFactory()
        self.intelligence = IntelligenceFactory(org=self.project.org)
        self.contentbase = ContentBaseFactory(intelligence=self.intelligence)

    def test_count_all_intelligence_content_use_case(self):
        use_case = ListAllIntelligenceContentUseCase()
        all_intelligence_content = use_case.get_project_intelligences(
            project_uuid=self.project.uuid,
            user_email=self.project.created_by.email
        )
        self.assertEqual(1, len(all_intelligence_content))
        self.assertEqual(1, len(all_intelligence_content[0]['content_bases']))
        self.assertEqual(str(self.contentbase.uuid), all_intelligence_content[0]['content_bases'][0]['uuid'])
        self.assertEqual(self.contentbase.title, all_intelligence_content[0]['content_bases'][0]['content_base_name'])
        self.assertEqual(self.intelligence.name, all_intelligence_content[0]['intelligence_name'])


class TestListContentBaseFileUseCase(TestCase):

    def setUp(self):
        self.contentbase = ContentBaseFactory()
        self.contentbase_file = ContentBaseFileFactory(
            content_base=self.contentbase
        )

    def test_count_contentbasefile_use_case(self):
        use_case = ListContentBaseFileUseCase()
        contentbasefile_list = use_case.get_contentbase_file(
            self.contentbase.uuid,
            user_email=self.contentbase.created_by.email
        )
        self.assertEqual(1, len(contentbasefile_list))


class TestGetLLMConfig(TestCase):

    def setUp(self) -> None:
        self.llm = LLMFactory()
        self.project_uuid = self.llm.intelligence.project.uuid
        self.created_by_email = self.llm.created_by.email

    def test_list_llm_config(self):

        llm_config = get_llm_config(
            project_uuid=self.project_uuid,
            user_email=self.created_by_email
        )
        self.assertEqual(1, len(llm_config))
