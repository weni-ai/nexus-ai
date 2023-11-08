from uuid import uuid4
from django.test import TestCase

from ..get_by_uuid import get_by_uuid
from ..exceptions import OrgDoesNotExists
from nexus.orgs.models import Org
from nexus.users.models import User


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

    def test_get_by_uuid(self):
        retrieved_org = get_by_uuid(self.org.uuid)
        self.assertEqual(self.org, retrieved_org)

    def test_get_by_uuid_nonexistent(self):
        with self.assertRaises(OrgDoesNotExists):
            get_by_uuid("nonexistent_uuid")

    def test_get_by_uuid_invalid(self):
        with self.assertRaises(OrgDoesNotExists):
            get_by_uuid(uuid4().hex)

    def test_get_by_uuid_none(self):
        with self.assertRaises(OrgDoesNotExists):
            get_by_uuid(None)
