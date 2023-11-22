from uuid import uuid4
from django.test import TestCase
from django.core.exceptions import ValidationError

from ..get_by_uuid import get_by_intelligence_uuid
from ..exceptions import IntelligenceDoesNotExist
from nexus.orgs.models import Org
from nexus.users.models import User
from nexus.intelligences.models import Intelligence


class GetByUuidTestCase(TestCase):

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

    def test_get_by_uuid(self):
        retrieved_intelligence = get_by_intelligence_uuid(
            self.intelligence.uuid
        )
        self.assertEqual(self.intelligence, retrieved_intelligence)

    def test_get_by_uuid_nonexistent(self):
        with self.assertRaises(ValidationError):
            get_by_intelligence_uuid("nonexistent_uuid")

    def test_get_by_uuid_invalid(self):
        with self.assertRaises(IntelligenceDoesNotExist):
            get_by_intelligence_uuid(uuid4().hex)

    def test_get_by_uuid_none(self):
        with self.assertRaises(IntelligenceDoesNotExist):
            get_by_intelligence_uuid(None)
