from uuid import uuid4
from django.test import TestCase
from django.core.exceptions import ValidationError

from ..get_by_uuid import (
    get_by_intelligence_uuid,
    get_by_contentbase_uuid,
    get_by_contentbasetext_uuid,
    get_contentbasetext_by_contentbase_uuid
)
from ..exceptions import (
    IntelligenceDoesNotExist,
    ContentBaseDoesNotExist,
    ContentBaseTextDoesNotExist
)
from .intelligence_factory import (
    IntelligenceFactory,
    ContentBaseFactory,
    ContentBaseTextFactory
)


class GetByIntelligenceUuidTestCase(TestCase):

    def setUp(self):
        self.intelligence = IntelligenceFactory()

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


class GetByContentBaseUuidTestCase(TestCase):

    def setUp(self):

        self.contentbase = ContentBaseFactory()

    def test_get_by_uuid(self):
        retrieved_contentbase = get_by_contentbase_uuid(
            self.contentbase.uuid
        )
        self.assertEqual(self.contentbase, retrieved_contentbase)

    def test_get_by_uuid_nonexistent(self):
        with self.assertRaises(ValidationError):
            get_by_contentbase_uuid("nonexistent_uuid")

    def test_get_by_uuid_invalid(self):
        with self.assertRaises(ContentBaseDoesNotExist):
            get_by_contentbase_uuid(uuid4().hex)

    def test_get_by_uuid_none(self):
        with self.assertRaises(ContentBaseDoesNotExist):
            get_by_contentbase_uuid(None)


class GetByContentBaseTextUuidTestCase(TestCase):

    def setUp(self):
        self.contentbasetext = ContentBaseTextFactory()

    def test_get_by_uuid(self):
        retrieved_contentbasetext = get_by_contentbasetext_uuid(
            self.contentbasetext.uuid
        )
        self.assertEqual(self.contentbasetext, retrieved_contentbasetext)

    def test_get_by_uuid_nonexistent(self):
        with self.assertRaises(ValidationError):
            get_by_contentbasetext_uuid("nonexistent_uuid")

    def test_get_by_uuid_invalid(self):
        with self.assertRaises(ContentBaseTextDoesNotExist):
            get_by_contentbasetext_uuid(uuid4().hex)

    def test_get_by_uuid_none(self):
        with self.assertRaises(ContentBaseTextDoesNotExist):
            get_by_contentbasetext_uuid(None)

    def test_get_contentbasetext_by_contentbase_uuid(self):
        retrieved_contentbasetext = get_contentbasetext_by_contentbase_uuid(
            self.contentbasetext.content_base.uuid
        )
        self.assertEqual(self.contentbasetext, retrieved_contentbasetext)
