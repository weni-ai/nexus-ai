from django.test import TestCase
from ..list import ListIntelligencesUseCase

from nexus.orgs.models import Org
from nexus.users.models import User
from nexus.intelligences.models import Intelligence


class TestListIntelligenceUseCase(TestCase):

    def setUp(self):
        self.user = User.objects.create(
            email='test3@user.com',
            language='en'
        )
        self.org = Org.objects.create(
            name='Test Org',
            created_by=self.user,
        )
        self.intelligence = Intelligence.objects.create(
            name='Test Intelligence',
            org=self.org,
            created_by=self.user,
        )

    def test_count_intelligence_use_case(self):
        use_case = ListIntelligencesUseCase()
        intelligences_list = use_case.get_org_intelligences(self.org.uuid)
        self.assertEqual(1, len(intelligences_list))
