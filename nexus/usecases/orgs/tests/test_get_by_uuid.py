from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase

from nexus.usecases.intelligences.exceptions import ContentBaseDoesNotExist
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory

from ..exceptions import OrgDoesNotExists
from ..get_by_uuid import get_by_uuid, get_org_by_content_base_uuid


class GetByUuidTestCase(TestCase):
    def setUp(self):
        self.content_base = ContentBaseFactory()
        self.org = self.content_base.intelligence.org

    def test_get_by_uuid(self):
        retrieved_org = get_by_uuid(self.org.uuid)
        self.assertEqual(self.org, retrieved_org)

    def test_get_by_uuid_nonexistent(self):
        with self.assertRaises(ValidationError):
            get_by_uuid("nonexistent_uuid")

    def test_get_by_uuid_invalid(self):
        with self.assertRaises(OrgDoesNotExists):
            get_by_uuid(uuid4().hex)

    def test_get_by_uuid_none(self):
        with self.assertRaises(OrgDoesNotExists):
            get_by_uuid(None)

    def test_get_org_by_content_base_uuid(self):
        retrieved_org = get_org_by_content_base_uuid(self.content_base.uuid)
        self.assertEqual(self.org, retrieved_org)

    def test_get_org_by_content_base_uuid_invalid(self):
        with self.assertRaises(ValidationError):
            get_org_by_content_base_uuid("nonexistent_uuid")

    def test_get_org_by_content_base_uuid_nonexistent(self):
        with self.assertRaises(ContentBaseDoesNotExist):
            get_org_by_content_base_uuid(uuid4().hex)
