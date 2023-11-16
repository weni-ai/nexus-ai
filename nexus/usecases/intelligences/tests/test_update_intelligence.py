from django.test import TestCase
from ..update import UpdateIntelligenceUseCase
from nexus.intelligences.models import Intelligence
from nexus.orgs.models import Org
from nexus.users.models import User


class TestUpdateIntelligenceUseCase(TestCase):

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
            description='Test Description',
            org=self.org,
            created_by=self.user
        )
        self.use_case = UpdateIntelligenceUseCase()

    def test_update_intelligence_name(self):
        new_name = 'New Intelligence Name'
        updated_intelligence = self.use_case.update_intelligences(
            intelligence_uuid=self.intelligence.uuid,
            name=new_name
        )
        self.assertEqual(updated_intelligence.name, new_name)

    def test_update_intelligence_description(self):
        new_description = 'New Intelligence Description'
        updated_intelligence = self.use_case.update_intelligences(
            intelligence_uuid=self.intelligence.uuid,
            description=new_description
        )
        self.assertEqual(updated_intelligence.description, new_description)

    def test_update_intelligence_name_and_description(self):
        new_name = 'New Intelligence Name'
        new_description = 'New Intelligence Description'
        updated_intelligence = self.use_case.update_intelligences(
            intelligence_uuid=self.intelligence.uuid,
            name=new_name,
            description=new_description
        )
        self.assertEqual(updated_intelligence.name, new_name)
        self.assertEqual(updated_intelligence.description, new_description)
