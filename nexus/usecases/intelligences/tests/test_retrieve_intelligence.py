from django.test import TestCase

from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText,
    ContentBaseFile,
    ContentBaseLink,
)
from ..retrieve import (
    RetrieveContentBaseTextUseCase,
    RetrieveContentBaseUseCase,
    RetrieveIntelligenceUseCase,
    RetrieveContentBaseLinkUseCase,
)
from .intelligence_factory import (
    IntelligenceFactory,
    ContentBaseFactory,
    ContentBaseTextFactory,
    ContentBaseFileFactory,
    ContentBaseLinkFactory,
    IntegratedIntelligenceFactory
)

from nexus.usecases.intelligences.retrieve import RetrieveContentBaseFileUseCase, get_file_info
from nexus.usecases.users.tests.user_factory import UserFactory
from nexus.usecases.intelligences.exceptions import IntelligencePermissionDenied

from nexus.projects.models import ProjectAuth


class TestRetrieveIntelligenceUseCase(TestCase):

    def setUp(self):
        self.intelligence = IntelligenceFactory()
        self.usecase = RetrieveIntelligenceUseCase()
        self.user = UserFactory()

    def test_count_intelligence_use_case(self):
        intelligences_retrieve = self.usecase.get_intelligence(
            intelligence_uuid=self.intelligence.uuid,
            user_email=self.intelligence.created_by.email
        )
        self.assertIsNotNone(intelligences_retrieve)
        self.assertIsInstance(intelligences_retrieve, Intelligence)

    def test_count_intelligence_use_case_fail(self):
        with self.assertRaises(IntelligencePermissionDenied):
            self.usecase.get_intelligence(
                intelligence_uuid=self.intelligence.uuid,
                user_email=self.user.email
            )


class TestRetrieveContentBaseUseCase(TestCase):

    def setUp(self):

        integrated_intelligence = IntegratedIntelligenceFactory()
        created_by = integrated_intelligence.intelligence.created_by

        self.project = integrated_intelligence.project
        self.contentbase = ContentBaseFactory(
            intelligence=integrated_intelligence.intelligence,
            created_by=created_by
        )
        self.router = ContentBaseFactory(
            intelligence=integrated_intelligence.intelligence,
            created_by=created_by,
            is_router=True
        )
        self.user = UserFactory()

        self.usecase = RetrieveContentBaseUseCase()

    def test_count_contentbase_use_case(self):
        contentbase_retrieve = self.usecase.get_contentbase(
            contentbase_uuid=self.contentbase.uuid,
            user_email=self.contentbase.created_by.email
        )
        self.assertIsNotNone(contentbase_retrieve)
        self.assertIsInstance(contentbase_retrieve, ContentBase)

    def test_get_contentbase_fail(self):
        with self.assertRaises(IntelligencePermissionDenied):
            self.usecase.get_contentbase(
                contentbase_uuid=self.contentbase.uuid,
                user_email=self.user.email
            )

    def test_get_default_by_project(self):
        contentbase_retrieve = self.usecase.get_default_by_project(
            project_uuid=self.project.uuid,
            user_email=self.router.created_by.email
        )
        self.assertIsNotNone(contentbase_retrieve)
        self.assertIsInstance(contentbase_retrieve, ContentBase)

    def test_get_default_by_project_fail(self):
        with self.assertRaises(ProjectAuth.DoesNotExist):
            self.usecase.get_default_by_project(
                project_uuid=self.project.uuid,
                user_email=self.user.email
            )


class TestRetrieveContentBaseTextUseCase(TestCase):

    def setUp(self):
        self.contentbasetext = ContentBaseTextFactory()
        self.fail_user = UserFactory()
        self.usecase = RetrieveContentBaseTextUseCase()

    def test_count_contentbasetext_use_case(self):
        contentbasetext_retrieve = self.usecase.get_contentbasetext(
            contentbasetext_uuid=self.contentbasetext.uuid,
            user_email=self.contentbasetext.created_by.email
        )
        self.assertIsNotNone(contentbasetext_retrieve)
        self.assertIsInstance(contentbasetext_retrieve, ContentBaseText)

    def test_retrieve_text_permission_denied(self):
        with self.assertRaises(IntelligencePermissionDenied):
            self.usecase.get_contentbasetext(str(self.contentbasetext.uuid), self.fail_user.email)

    def test_get_file_text_info(self):
        file_uuid = str(self.contentbasetext.uuid)
        file_info = get_file_info(file_uuid)
        self.assertEquals(file_info.get("uuid"), file_uuid)


class RetrieveContentBaseFileUseCaseTestCase(TestCase):
    def setUp(self) -> None:
        self.content_base_file = ContentBaseFileFactory()
        self.content_base = self.content_base_file.content_base
        self.org = self.content_base.intelligence.org
        self.user = UserFactory()
        self.org_auth = self.org.authorizations.create(user=self.user, role=3)
        self.fail_user = UserFactory()
        self.usecase = RetrieveContentBaseFileUseCase()

    def test_retrieve_file(self):
        file = self.usecase.get_contentbasefile(str(self.content_base_file.uuid), self.user.email)
        self.assertIsInstance(file, ContentBaseFile)

    def test_retrieve_file_permission_denied(self):
        with self.assertRaises(IntelligencePermissionDenied):
            self.usecase.get_contentbasefile(str(self.content_base_file.uuid), self.fail_user.email)

    def test_get_file_info(self):
        file_uuid = str(self.content_base_file.uuid)
        file_info = get_file_info(file_uuid)
        self.assertEquals(file_info.get("uuid"), file_uuid)


class RetrieveContentBaseLinkUseCaseTestCase(TestCase):
    def setUp(self) -> None:
        self.content_base_link = ContentBaseLinkFactory()
        self.content_base = self.content_base_link.content_base
        self.org = self.content_base.intelligence.org
        self.user = UserFactory()
        self.org_auth = self.org.authorizations.create(user=self.user, role=3)
        self.fail_user = UserFactory()
        self.usecase = RetrieveContentBaseLinkUseCase()

    def test_retrieve_link(self):
        file = self.usecase.get_contentbaselink(str(self.content_base_link.uuid), self.user.email)
        self.assertIsInstance(file, ContentBaseLink)

    def test_retrieve_link_permission_denied(self):
        with self.assertRaises(IntelligencePermissionDenied):
            self.usecase.get_contentbaselink(str(self.content_base_link.uuid), self.fail_user.email)
