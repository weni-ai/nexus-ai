from datetime import timedelta
from unittest import mock

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from nexus.projects.exceptions import ProjectApiTokenNameAlreadyExists, ProjectDoesNotExist
from nexus.projects.models import ProjectApiToken
from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory
from nexus.usecases.projects.project_api_token import ProjectApiTokenUseCase


class TestProjectApiTokenUseCase(TestCase):
    def setUp(self):
        integrated_intelligence = IntegratedIntelligenceFactory()
        self.project = integrated_intelligence.project
        self.user = self.project.created_by
        self.use_case = ProjectApiTokenUseCase()

    def test_create_token_with_defaults(self):
        before = timezone.now()
        api_token, plaintext = self.use_case.create_token(
            project=self.project,
            created_by=self.user,
        )
        after = timezone.now()

        self.assertTrue(plaintext)
        self.assertNotEqual(plaintext, api_token.token_hash)
        self.assertTrue(api_token.name.startswith("Auto "))
        self.assertEqual(api_token.scope, ProjectApiTokenUseCase.DEFAULT_SCOPE)
        self.assertTrue(api_token.enabled)
        self.assertEqual(api_token.created_by, self.user)
        self.assertTrue(api_token.matches(plaintext))
        self.assertGreaterEqual(api_token.expires_at, before + timedelta(days=364))
        self.assertLessEqual(api_token.expires_at, after + timedelta(days=365))

    def test_create_token_with_custom_name_and_scope(self):
        api_token, plaintext = self.use_case.create_token(
            project_uuid=str(self.project.uuid),
            name="supervisor-public",
            scope="read:supervisor_conversations",
            created_by=self.user,
        )

        self.assertEqual(api_token.name, "supervisor-public")
        self.assertEqual(api_token.scope, "read:supervisor_conversations")
        self.assertTrue(api_token.matches(plaintext))

    def test_create_token_duplicate_name_raises(self):
        self.use_case.create_token(project=self.project, name="same-name", created_by=self.user)

        with self.assertRaises(ProjectApiTokenNameAlreadyExists):
            self.use_case.create_token(project=self.project, name="same-name", created_by=self.user)

        self.assertEqual(ProjectApiToken.objects.filter(project=self.project, name="same-name").count(), 1)

    def test_create_token_missing_project_raises(self):
        with self.assertRaises(ProjectDoesNotExist):
            self.use_case.create_token()

    def test_serialize_created_token_includes_plaintext_only(self):
        api_token, plaintext = self.use_case.create_token(project=self.project, name="serialize-me")
        payload = self.use_case.serialize_created_token(api_token, plaintext)

        self.assertEqual(payload["id"], api_token.id)
        self.assertEqual(payload["token"], plaintext)
        self.assertEqual(payload["name"], "serialize-me")
        self.assertNotIn("token_hash", payload)
        self.assertNotIn("salt", payload)

    def test_integrity_error_duplicate_is_mapped_to_domain_exception(self):
        with mock.patch(
            "nexus.usecases.projects.project_api_token.ProjectApiToken.objects.create",
            side_effect=IntegrityError("UNIQUE constraint failed: project_id, name"),
        ):
            with self.assertRaises(ProjectApiTokenNameAlreadyExists):
                self.use_case.create_token(project=self.project, name="boom")

    def test_unrelated_integrity_error_is_re_raised(self):
        with mock.patch(
            "nexus.usecases.projects.project_api_token.ProjectApiToken.objects.create",
            side_effect=IntegrityError("NOT NULL constraint failed: some_other_column"),
        ):
            with self.assertRaises(IntegrityError):
                self.use_case.create_token(project=self.project, name="boom")

    def test_invalid_project_uuid_raises_project_does_not_exist(self):
        with self.assertRaises(ProjectDoesNotExist):
            self.use_case.create_token(project_uuid="not-a-uuid", name="x")

    def test_default_names_are_unique_within_same_second(self):
        first, _ = self.use_case.create_token(project=self.project, created_by=self.user)
        second, _ = self.use_case.create_token(project=self.project, created_by=self.user)
        self.assertNotEqual(first.name, second.name)
        self.assertTrue(first.name.startswith("Auto "))
        self.assertTrue(second.name.startswith("Auto "))
