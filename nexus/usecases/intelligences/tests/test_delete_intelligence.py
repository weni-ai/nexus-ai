from django.test import TestCase
from ..delete import (
    DeleteIntelligenceUseCase,
    DeleteContentBaseUseCase,
    DeleteContentBaseTextUseCase
)
from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText
)
from .intelligence_factory import (
    IntelligenceFactory,
    ContentBaseFactory,
    ContentBaseTextFactory
)
from nexus.event_domain.recent_activity.mocks import mock_message_handler, mock_event_manager_notify
from nexus.usecases.intelligences.tests.mocks import MockFileDataBase

class TestDeleteIntelligenceUseCase(TestCase):
    def setUp(self):
        self.use_case = DeleteIntelligenceUseCase(
            recent_activity_message=mock_message_handler
        )
        self.intelligence = IntelligenceFactory()

    def test_delete_intelligence(self):
        self.use_case.delete_intelligences(
            intelligence_uuid=self.intelligence.uuid,
            user_email=self.intelligence.created_by.email
        )
        self.assertEqual(Intelligence.objects.count(), 0)


class TestDeleteContentBaseUseCase(TestCase):

    def setUp(self):
        self.contentbase = ContentBaseFactory()

    def test_delete_contentbase(self):
        use_case = DeleteContentBaseUseCase(
            event_manager_notify=mock_event_manager_notify
        )
        use_case.delete_contentbase(
            contentbase_uuid=self.contentbase.uuid,
            user_email=self.contentbase.created_by.email
        )
        self.assertEqual(ContentBase.objects.count(), 0)


class TestDeleteContentBaseTextUseCase(TestCase):

    def setUp(self):
        self.contentbasetext = ContentBaseTextFactory()

    def test_delete_contentbasetext(self):
        use_case = DeleteContentBaseTextUseCase(file_database=MockFileDataBase())
        status = use_case.delete_contentbasetext(
            contentbasetext_uuid=self.contentbasetext.uuid,
            user_email=self.contentbasetext.created_by.email
        )
        self.assertEqual(ContentBaseText.objects.count(), 0)
        self.assertTrue(status)
