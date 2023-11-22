from django.test import TestCase
from ..delete import DeleteIntelligenceUseCase, DeleteContentBaseUseCase
from nexus.intelligences.models import Intelligence, ContentBase
from nexus.orgs.models import Org
from nexus.users.models import User


class TestDeleteIntelligenceUseCase(TestCase):
    def setUp(self):
        self.use_case = DeleteIntelligenceUseCase()
        self.user = User.objects.create(
            email='test_org@user.com',
            language='en'
        )
        self.org = Org.objects.create(
            name='Test Org',
            created_by=self.user,
        )
        self.intelligence = Intelligence.objects.create(
            name='Test Intelligence',
            created_by=self.user,
            org=self.org
        )

    def test_delete_intelligence(self):
        self.use_case.delete_intelligences(self.intelligence.uuid)
        self.assertEqual(Intelligence.objects.count(), 0)


class TestDeleteContentBaseUseCase(TestCase):

    def setUp(self):

        self.user = User.objects.create(
            email='test_org@user.com',
            language='en'
        )
        self.org = Org.objects.create(
            name='Test Org',
            created_by=self.user,
        )
        self.intelligence = Intelligence.objects.create(
            name='Test Intelligence',
            created_by=self.user,
            org=self.org
        )
        self.contentbase = ContentBase.objects.create(
            intelligence=self.intelligence,
            created_by=self.user,
            title="title"
        )

    def test_delete_contentbase(self):
        use_case = DeleteContentBaseUseCase()
        use_case.delete_contentbase(self.contentbase.uuid)
        self.assertEqual(ContentBase.objects.count(), 0)
