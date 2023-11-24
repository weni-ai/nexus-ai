from django.test import TestCase
from ..create import CreateIntelligencesUseCase

from nexus.orgs.models import Org
from nexus.users.models import User


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

    def test_create_intelligence_use_case(self):
        use_case = CreateIntelligencesUseCase()
        intelligences_create = use_case.create_intelligences(
            name="name",
            description="description",
            org_uuid=self.org.uuid,
            user_email=self.user.email
        )
        self.assertEqual(intelligences_create.name, "name")
