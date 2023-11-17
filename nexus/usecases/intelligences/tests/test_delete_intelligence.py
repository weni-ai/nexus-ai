from django.test import TestCase
from ..delete import DeleteIntelligenceUseCase
from nexus.intelligences.models import Intelligence
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
