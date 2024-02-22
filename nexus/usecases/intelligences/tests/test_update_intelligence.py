from django.test import TestCase
from ..update import (
    UpdateIntelligenceUseCase,
    UpdateContentBaseUseCase,
    UpdateContentBaseTextUseCase
)
from .intelligence_factory import (
    IntelligenceFactory,
    ContentBaseFactory,
    ContentBaseTextFactory
)


class TestUpdateIntelligenceUseCase(TestCase):

    def setUp(self):
        self.intelligence = IntelligenceFactory()
        self.use_case = UpdateIntelligenceUseCase()

    def test_update_intelligence_name(self):
        new_name = 'New Intelligence Name'
        updated_intelligence = self.use_case.update_intelligences(
            intelligence_uuid=self.intelligence.uuid,
            name=new_name,
            user_email=self.intelligence.created_by.email
        )
        self.assertEqual(updated_intelligence.name, new_name)

    def test_update_intelligence_description(self):
        new_description = 'New Intelligence Description'
        updated_intelligence = self.use_case.update_intelligences(
            intelligence_uuid=self.intelligence.uuid,
            description=new_description,
            user_email=self.intelligence.created_by.email
        )
        self.assertEqual(updated_intelligence.description, new_description)

    def test_update_intelligence_name_and_description(self):
        new_name = 'New Intelligence Name'
        new_description = 'New Intelligence Description'
        updated_intelligence = self.use_case.update_intelligences(
            intelligence_uuid=self.intelligence.uuid,
            name=new_name,
            description=new_description,
            user_email=self.intelligence.created_by.email
        )
        self.assertEqual(updated_intelligence.name, new_name)
        self.assertEqual(updated_intelligence.description, new_description)


class TestUpdateContentBaseUseCase(TestCase):

    def setUp(self):
        self.contentbase = ContentBaseFactory()

    def test_update_contentbase_title(self):
        new_title = 'New Title'
        new_language = 'pt-br'
        use_case = UpdateContentBaseUseCase()
        updated_contentbase = use_case.update_contentbase(
            contentbase_uuid=self.contentbase.uuid,
            title=new_title,
            user_email=self.contentbase.created_by.email,
            language=new_language
        )
        self.assertEqual(updated_contentbase.title, new_title)
        self.assertEqual(updated_contentbase.language, new_language)


class TestUpdateContentBaseTextUseCase(TestCase):

    def setUp(self):
        self.contentbasetext = ContentBaseTextFactory()

    def test_update_contentbasetext_text(self):
        new_text = 'New Text'
        use_case = UpdateContentBaseTextUseCase()
        updated_contentbasetext = use_case.update_contentbasetext(
            contentbasetext_uuid=self.contentbasetext.uuid,
            text=new_text,
            user_email=self.contentbasetext.created_by.email
        )
        self.assertEqual(updated_contentbasetext.text, new_text)
