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
from nexus.usecases.orgs.tests.org_factory import OrgFactory, OrgAuthFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class TestDeleteIntelligenceUseCase(TestCase):
    def setUp(self):
        self.use_case = DeleteIntelligenceUseCase()
        self.user = UserFactory()
        self.org = OrgFactory(created_by=self.user)
        self.org_auth = OrgAuthFactory(org=self.org, user=self.user)
        self.intelligence = IntelligenceFactory(
            org=self.org,
            created_by=self.user
        )

    def test_delete_intelligence(self):
        self.use_case.delete_intelligences(
            self.intelligence.uuid,
            self.user.email
        )
        self.assertEqual(Intelligence.objects.count(), 0)


class TestDeleteContentBaseUseCase(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.org = OrgFactory(created_by=self.user)
        self.auth = OrgAuthFactory(org=self.org, user=self.user)
        self.intelligence = IntelligenceFactory(
            org=self.org,
            created_by=self.user
        )
        self.contentbase = ContentBaseFactory(
            intelligence=self.intelligence
        )

    def test_delete_contentbase(self):
        use_case = DeleteContentBaseUseCase()
        use_case.delete_contentbase(
            self.contentbase.uuid,
            self.user.email
        )
        self.assertEqual(ContentBase.objects.count(), 0)


class TestDeleteContentBaseTextUseCase(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.org = OrgFactory(created_by=self.user)
        self.auth = OrgAuthFactory(org=self.org, user=self.user)
        self.intelligence = IntelligenceFactory(
            org=self.org,
            created_by=self.user
        )
        self.contentbase = ContentBaseFactory(intelligence=self.intelligence)
        self.contentbasetext = ContentBaseTextFactory(
            content_base=self.contentbase,
            created_by=self.user
        )

    def test_delete_contentbasetext(self):
        use_case = DeleteContentBaseTextUseCase()
        status = use_case.delete_contentbasetext(
            contentbasetext_uuid=self.contentbasetext.uuid,
            user_email=self.user.email
        )
        self.assertEqual(ContentBaseText.objects.count(), 0)
        self.assertTrue(status)
