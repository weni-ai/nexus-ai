from unittest.mock import patch

import requests
from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from nexus.agents.encryption import encrypt_value
from nexus.inline_agents.backends.openai.models import (
    ManagerAgent,
    ModelProvider,
    ProjectModelProvider,
    project_has_api_visible_own_engine,
)
from nexus.inline_agents.backends.openai.repository import ManagerAgentRepository
from nexus.usecases.projects.tests.project_factory import ProjectFactory

TEST_ENCRYPTION_KEY = Fernet.generate_key()


def _create_manager(model_vendor="openai", **kwargs):
    defaults = dict(
        name="Test Manager",
        base_prompt="You are a manager.",
        foundation_model="gpt-4o",
        model_vendor=model_vendor,
        release_date=timezone.now(),
        collaborators_foundation_model="gpt-4o-mini",
        formatter_agent_foundation_model="gpt-4o-mini",
    )
    defaults.update(kwargs)
    return ManagerAgent.objects.create(**defaults)


def _create_provider(model_vendor="openai", manager_agent=None):
    schema_map = {
        "openai": {
            "label": "OpenAI",
            "credentials": [
                {"id": "api_key", "label": "API key", "type": "PASSWORD"},
                {"id": "api_base", "label": "API base URL", "type": "TEXT"},
            ],
        },
        "gemini": {
            "label": "Google Gemini",
            "credentials": [
                {"id": "api_key", "label": "API key", "type": "PASSWORD"},
            ],
        },
        "vertex_ai": {
            "label": "Vertex AI",
            "credentials": [
                {"id": "service_account_json", "label": "Service account JSON", "type": "TEXTAREA"},
            ],
        },
    }
    data = schema_map[model_vendor]
    return ModelProvider.objects.create(
        model_vendor=model_vendor,
        label=data["label"],
        credentials=data["credentials"],
        manager_agent=manager_agent,
    )


@override_settings(CREDENTIAL_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY)
class TestProjectModelProviderEncryption(TestCase):
    def setUp(self):
        self.project = ProjectFactory(name="EncryptProject")
        self.manager = _create_manager("openai")
        self.provider = _create_provider("openai", manager_agent=self.manager)

    def test_encrypt_and_decrypt_credentials(self):
        pmp = ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.provider,
            credentials=[
                {"id": "api_key", "type": "PASSWORD", "label": "API key", "value": "sk-secret-key-1234"},
                {"id": "api_base", "type": "TEXT", "label": "API base URL", "value": "https://api.example.com"},
            ],
        )
        pmp.encrypt_credentials()
        pmp.save()

        pmp.refresh_from_db()
        raw_creds = pmp.credentials
        api_key_entry = next(f for f in raw_creds if f["id"] == "api_key")
        self.assertNotEqual(api_key_entry["value"], "sk-secret-key-1234")

        api_base_entry = next(f for f in raw_creds if f["id"] == "api_base")
        self.assertEqual(api_base_entry["value"], "https://api.example.com")

        decrypted = pmp.decrypted_credentials
        dk = next(f for f in decrypted if f["id"] == "api_key")
        self.assertEqual(dk["value"], "sk-secret-key-1234")

        db = next(f for f in decrypted if f["id"] == "api_base")
        self.assertEqual(db["value"], "https://api.example.com")

    def test_masked_credentials_password(self):
        pmp = ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.provider,
            credentials=[
                {
                    "id": "api_key",
                    "type": "PASSWORD",
                    "label": "API key",
                    "value": encrypt_value("sk-longapikey1234567890"),
                },
                {"id": "api_base", "type": "TEXT", "label": "API base URL", "value": "https://api.example.com"},
            ],
        )
        schema = self.provider.credentials
        masked = pmp.masked_credentials(schema)

        api_key_masked = next(f for f in masked if f["id"] == "api_key")
        self.assertIn("...", api_key_masked["value"])
        self.assertNotEqual(api_key_masked["value"], "sk-longapikey1234567890")

        api_base_masked = next(f for f in masked if f["id"] == "api_base")
        self.assertEqual(api_base_masked["value"], "https://api.example.com")

    def test_masked_credentials_textarea_returns_empty(self):
        vertex_manager = _create_manager("vertex_ai")
        provider = _create_provider("vertex_ai", manager_agent=vertex_manager)
        pmp = ProjectModelProvider.objects.create(
            project=self.project,
            provider=provider,
            credentials=[
                {
                    "id": "service_account_json",
                    "type": "TEXTAREA",
                    "label": "Service account JSON",
                    "value": encrypt_value('{"type":"service_account"}'),
                },
            ],
        )
        schema = provider.credentials
        masked = pmp.masked_credentials(schema)
        sa_masked = next(f for f in masked if f["id"] == "service_account_json")
        self.assertEqual(sa_masked["value"], "")


class TestProviderSelectsManager(TestCase):
    """POST /model-providers switches the project's manager_agent to the provider's manager."""

    def setUp(self):
        self.project = ProjectFactory(name="ProviderSelectsProject")
        self.openai_manager = _create_manager(model_vendor="openai", name="OpenAI Manager")
        self.gemini_manager = _create_manager(model_vendor="gemini", name="Gemini Manager")
        self.openai_provider = _create_provider("openai", manager_agent=self.openai_manager)
        self.gemini_provider = _create_provider("gemini", manager_agent=self.gemini_manager)

    def test_saving_credentials_updates_project_manager(self):
        self.project.manager_agent = self.openai_manager
        self.project.save()

        ProjectModelProvider.objects.update_or_create(
            project=self.project,
            provider=self.gemini_provider,
            defaults={"credentials": [{"id": "api_key", "value": "gem-key"}], "is_active": True},
        )
        self.project.manager_agent = self.gemini_provider.manager_agent
        self.project.save()

        self.project.refresh_from_db()
        self.assertEqual(self.project.manager_agent_id, self.gemini_manager.id)

    def test_deactivates_previous_provider_on_switch(self):
        openai_pmp = ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.openai_provider,
            credentials=[{"id": "api_key", "value": "sk-test"}],
            is_active=True,
        )

        ProjectModelProvider.objects.filter(project=self.project, is_active=True).exclude(
            provider=self.gemini_provider
        ).update(is_active=False)

        ProjectModelProvider.objects.update_or_create(
            project=self.project,
            provider=self.gemini_provider,
            defaults={"credentials": [{"id": "api_key", "value": "gem-key"}], "is_active": True},
        )

        openai_pmp.refresh_from_db()
        self.assertFalse(openai_pmp.is_active)

        gemini_pmp = ProjectModelProvider.objects.get(project=self.project, provider=self.gemini_provider)
        self.assertTrue(gemini_pmp.is_active)

    def test_project_without_manager_can_set_provider(self):
        self.assertIsNone(self.project.manager_agent)

        ProjectModelProvider.objects.update_or_create(
            project=self.project,
            provider=self.openai_provider,
            defaults={"credentials": [{"id": "api_key", "value": "sk-test"}], "is_active": True},
        )
        self.project.manager_agent = self.openai_provider.manager_agent
        self.project.save()

        self.project.refresh_from_db()
        self.assertEqual(self.project.manager_agent_id, self.openai_manager.id)


class TestDeleteRevertsToDefaultManager(TestCase):
    """DELETE /model-providers deactivates credentials and reverts manager to default."""

    def setUp(self):
        self.project = ProjectFactory(name="DeleteRevertProject")
        self.default_manager = _create_manager(model_vendor="openai", name="Default Manager", default=True, public=True)
        self.gemini_manager = _create_manager(model_vendor="gemini", name="Gemini Manager")
        self.gemini_provider = _create_provider("gemini", manager_agent=self.gemini_manager)

    def test_delete_deactivates_and_reverts_manager(self):
        self.project.manager_agent = self.gemini_manager
        self.project.save()

        pmp = ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.gemini_provider,
            credentials=[{"id": "api_key", "value": "gem-key"}],
            is_active=True,
        )

        ProjectModelProvider.objects.filter(project=self.project, is_active=True).update(is_active=False)

        default = ManagerAgent.objects.filter(default=True, public=True).order_by("created_on").last()
        self.project.manager_agent = default
        self.project.save()

        pmp.refresh_from_db()
        self.assertFalse(pmp.is_active)

        self.project.refresh_from_db()
        self.assertEqual(self.project.manager_agent_id, self.default_manager.id)

    def test_delete_returns_none_when_no_active_credentials(self):
        updated = ProjectModelProvider.objects.filter(project=self.project, is_active=True).update(is_active=False)
        self.assertEqual(updated, 0)


@override_settings(CREDENTIAL_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY)
class TestManagerAgentRepositoryProjectCredentials(TestCase):
    def setUp(self):
        self.project = ProjectFactory(name="RepoTestProject")
        self.manager = _create_manager(model_vendor="openai")
        self.project.manager_agent = self.manager
        self.project.save()
        self.provider = _create_provider("openai", manager_agent=self.manager)

    def test_uses_project_credentials_when_active(self):
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.provider,
            credentials=[
                {"id": "api_key", "type": "PASSWORD", "label": "API key", "value": encrypt_value("proj-api-key-123")},
                {"id": "api_base", "type": "TEXT", "label": "API base URL", "value": "https://proj.example.com"},
            ],
            is_active=True,
        )

        repo = ManagerAgentRepository()
        result = repo.get_supervisor(
            supervisor_agent_uuid=str(self.manager.uuid),
            project_uuid=str(self.project.uuid),
        )

        creds = result["user_model_credentials"]
        self.assertEqual(creds["api_key"], "proj-api-key-123")
        self.assertEqual(creds["api_base"], "https://proj.example.com")

    def test_passes_through_whirlpool_oauth_credentials(self):
        whirlpool_manager = _create_manager(model_vendor="whirlpool", name="Whirlpool Manager")
        whirlpool_provider = ModelProvider.objects.create(
            model_vendor="whirlpool",
            label="Whirlpool",
            credentials=[
                {"id": "client_id", "label": "Client ID", "type": "PASSWORD"},
                {"id": "client_secret", "label": "Client secret", "type": "PASSWORD"},
                {"id": "token_url", "label": "OAuth token URL", "type": "TEXT"},
                {"id": "generate_content_url", "label": "generateContent URL", "type": "TEXT"},
            ],
            manager_agent=whirlpool_manager,
        )
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=whirlpool_provider,
            credentials=[
                {
                    "id": "client_id",
                    "type": "PASSWORD",
                    "label": "Client ID",
                    "value": encrypt_value("whirlpool-client-id"),
                },
                {
                    "id": "client_secret",
                    "type": "PASSWORD",
                    "label": "Client secret",
                    "value": encrypt_value("whirlpool-client-secret"),
                },
                {
                    "id": "token_url",
                    "type": "TEXT",
                    "label": "OAuth token URL",
                    "value": "https://api-dev.whirlpool.com/oauth2/v1/token",
                },
                {
                    "id": "generate_content_url",
                    "type": "TEXT",
                    "label": "generateContent URL",
                    "value": "https://api-dev.whirlpool.com/d2c/cxplatform/v1/ai/generateContent",
                },
            ],
            is_active=True,
        )

        repo = ManagerAgentRepository()
        result = repo.get_supervisor(
            supervisor_agent_uuid=str(whirlpool_manager.uuid),
            project_uuid=str(self.project.uuid),
        )

        creds = result["user_model_credentials"]
        self.assertEqual(creds["client_id"], "whirlpool-client-id")
        self.assertEqual(creds["client_secret"], "whirlpool-client-secret")
        self.assertEqual(creds["token_url"], "https://api-dev.whirlpool.com/oauth2/v1/token")
        self.assertEqual(
            creds["generate_content_url"],
            "https://api-dev.whirlpool.com/d2c/cxplatform/v1/ai/generateContent",
        )

    def test_falls_back_to_manager_credentials_when_inactive(self):
        self.manager.api_key = "manager-key"
        self.manager.api_base = "https://manager.example.com"
        self.manager.api_version = "v1"
        self.manager.save()

        ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.provider,
            credentials=[
                {"id": "api_key", "type": "PASSWORD", "label": "API key", "value": encrypt_value("proj-key")},
            ],
            is_active=False,
        )

        repo = ManagerAgentRepository()
        result = repo.get_supervisor(
            supervisor_agent_uuid=str(self.manager.uuid),
            project_uuid=str(self.project.uuid),
        )

        creds = result["user_model_credentials"]
        self.assertEqual(creds["api_key"], "manager-key")
        self.assertEqual(creds["api_base"], "https://manager.example.com")

    def test_falls_back_to_manager_when_no_project_credential(self):
        self.manager.api_key = "mgr-key"
        self.manager.api_base = ""
        self.manager.api_version = ""
        self.manager.save()

        repo = ManagerAgentRepository()
        result = repo.get_supervisor(
            supervisor_agent_uuid=str(self.manager.uuid),
            project_uuid=str(self.project.uuid),
        )

        creds = result["user_model_credentials"]
        self.assertEqual(creds["api_key"], "mgr-key")

    def test_empty_credentials_when_no_project_and_no_manager_key(self):
        repo = ManagerAgentRepository()
        result = repo.get_supervisor(
            supervisor_agent_uuid=str(self.manager.uuid),
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(result["user_model_credentials"], {})

    def test_no_project_uuid_falls_back(self):
        self.manager.api_key = "mgr-key-fallback"
        self.manager.api_base = ""
        self.manager.api_version = ""
        self.manager.save()

        repo = ManagerAgentRepository()
        result = repo.get_supervisor(
            supervisor_agent_uuid=str(self.manager.uuid),
        )

        creds = result["user_model_credentials"]
        self.assertEqual(creds["api_key"], "mgr-key-fallback")


class TestEngineSourceLogic(TestCase):
    def setUp(self):
        self.project = ProjectFactory(name="EngineSourceProject")
        self.manager = _create_manager(model_vendor="openai")
        self.project.manager_agent = self.manager
        self.project.save()
        self.provider = _create_provider("openai", manager_agent=self.manager)

    def test_standard_when_no_credentials(self):
        self.assertFalse(project_has_api_visible_own_engine(self.project))

    def test_own_when_active_credentials(self):
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.provider,
            credentials=[
                {"id": "api_key", "type": "PASSWORD", "label": "API key", "value": "sk-test"},
            ],
            is_active=True,
        )
        self.assertTrue(project_has_api_visible_own_engine(self.project))

    def test_standard_when_inactive_credentials(self):
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.provider,
            credentials=[
                {"id": "api_key", "type": "PASSWORD", "label": "API key", "value": "sk-test"},
            ],
            is_active=False,
        )
        self.assertFalse(project_has_api_visible_own_engine(self.project))

    def test_standard_when_only_hidden_whirlpool_credentials(self):
        whirlpool_manager = _create_manager(model_vendor="whirlpool", name="Whirlpool Manager", public=False)
        whirlpool_provider = ModelProvider.objects.create(
            model_vendor="whirlpool",
            label="Whirlpool",
            credentials=[{"id": "client_id", "label": "Client ID", "type": "PASSWORD"}],
            manager_agent=whirlpool_manager,
        )
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=whirlpool_provider,
            credentials=[{"id": "client_id", "type": "PASSWORD", "label": "Client ID", "value": "cid"}],
            is_active=True,
        )
        self.assertFalse(project_has_api_visible_own_engine(self.project))


@override_settings(CREDENTIAL_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY)
class TestVertexAICredentialInjection(TestCase):
    def setUp(self):
        self.project = ProjectFactory(name="VertexProject")
        self.manager = _create_manager(model_vendor="vertex_ai")
        self.project.manager_agent = self.manager
        self.project.save()
        self.provider = _create_provider("vertex_ai", manager_agent=self.manager)

    def test_injects_vertex_credentials_into_extra_args(self):
        sa_json = '{"type":"service_account","project_id":"my-proj"}'
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.provider,
            credentials=[
                {
                    "id": "service_account_json",
                    "type": "TEXTAREA",
                    "label": "Service account JSON",
                    "value": encrypt_value(sa_json),
                },
            ],
            is_active=True,
        )

        repo = ManagerAgentRepository()
        result = repo.get_supervisor(
            supervisor_agent_uuid=str(self.manager.uuid),
            project_uuid=str(self.project.uuid),
        )

        extra_args = result["model_settings"]["manager_extra_args"]
        self.assertEqual(extra_args["vertex_credentials"], sa_json)

    def test_injects_vertex_project_and_location(self):
        sa_json = '{"type":"service_account"}'
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.provider,
            credentials=[
                {
                    "id": "service_account_json",
                    "type": "TEXTAREA",
                    "label": "Service account JSON",
                    "value": encrypt_value(sa_json),
                },
                {"id": "vertex_project", "type": "TEXT", "label": "Project ID", "value": "my-gcp-project"},
                {"id": "vertex_location", "type": "TEXT", "label": "Location", "value": "us-central1"},
            ],
            is_active=True,
        )

        repo = ManagerAgentRepository()
        result = repo.get_supervisor(
            supervisor_agent_uuid=str(self.manager.uuid),
            project_uuid=str(self.project.uuid),
        )

        extra_args = result["model_settings"]["manager_extra_args"]
        self.assertEqual(extra_args["vertex_credentials"], sa_json)
        self.assertEqual(extra_args["vertex_project"], "my-gcp-project")
        self.assertEqual(extra_args["vertex_location"], "us-central1")

    def test_no_injection_when_inactive(self):
        sa_json = '{"type":"service_account"}'
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.provider,
            credentials=[
                {
                    "id": "service_account_json",
                    "type": "TEXTAREA",
                    "label": "Service account JSON",
                    "value": encrypt_value(sa_json),
                },
            ],
            is_active=False,
        )

        repo = ManagerAgentRepository()
        result = repo.get_supervisor(
            supervisor_agent_uuid=str(self.manager.uuid),
            project_uuid=str(self.project.uuid),
        )

        extra_args = result["model_settings"]["manager_extra_args"]
        self.assertNotIn("vertex_credentials", extra_args)

    def test_preserves_existing_manager_extra_args(self):
        self.manager.manager_extra_args = {"some_existing_key": "some_value"}
        self.manager.save()

        sa_json = '{"type":"service_account"}'
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.provider,
            credentials=[
                {
                    "id": "service_account_json",
                    "type": "TEXTAREA",
                    "label": "Service account JSON",
                    "value": encrypt_value(sa_json),
                },
            ],
            is_active=True,
        )

        repo = ManagerAgentRepository()
        result = repo.get_supervisor(
            supervisor_agent_uuid=str(self.manager.uuid),
            project_uuid=str(self.project.uuid),
        )

        extra_args = result["model_settings"]["manager_extra_args"]
        self.assertEqual(extra_args["some_existing_key"], "some_value")
        self.assertEqual(extra_args["vertex_credentials"], sa_json)

    def test_no_injection_for_non_vertex_vendor(self):
        openai_project = ProjectFactory(name="OpenAIProject")
        openai_manager = _create_manager(model_vendor="openai")
        openai_project.manager_agent = openai_manager
        openai_project.save()

        openai_provider = _create_provider("openai", manager_agent=openai_manager)
        ProjectModelProvider.objects.create(
            project=openai_project,
            provider=openai_provider,
            credentials=[
                {"id": "api_key", "type": "PASSWORD", "label": "API key", "value": encrypt_value("sk-test")},
            ],
            is_active=True,
        )

        repo = ManagerAgentRepository()
        result = repo.get_supervisor(
            supervisor_agent_uuid=str(openai_manager.uuid),
            project_uuid=str(openai_project.uuid),
        )

        extra_args = result["model_settings"]["manager_extra_args"]
        self.assertNotIn("vertex_credentials", extra_args)


@override_settings(CREDENTIAL_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY)
class TestWhirlpoolHiddenFromModelProvidersApi(TestCase):
    def setUp(self):
        self.project = ProjectFactory(name="HiddenProviderProject")
        self.user = self.project.created_by
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.openai_manager = _create_manager(model_vendor="openai", name="OpenAI Manager", public=True)
        self.openai_provider = _create_provider("openai", manager_agent=self.openai_manager)
        self.whirlpool_manager = _create_manager(
            model_vendor="whirlpool",
            name="Whirlpool Manager",
            default=False,
            public=False,
        )
        self.whirlpool_provider = ModelProvider.objects.create(
            model_vendor="whirlpool",
            label="Whirlpool",
            credentials=[
                {"id": "client_id", "label": "Client ID", "type": "PASSWORD"},
                {"id": "client_secret", "label": "Client secret", "type": "PASSWORD"},
            ],
            manager_agent=self.whirlpool_manager,
        )
        self.url = reverse("project-model-providers", kwargs={"project_uuid": str(self.project.uuid)})
        self.engine_url = reverse("project-engine-source", kwargs={"project_uuid": str(self.project.uuid)})
        self.managers_url = reverse("project-agent-managers", kwargs={"project_uuid": str(self.project.uuid)})

    def _auth_ok(self, mock_check_auth):
        mock_check_auth.side_effect = requests.RequestException("Mocked external auth failure")

    @patch("nexus.projects.permissions._check_project_authorization")
    def test_get_omits_whirlpool_from_providers_and_current(self, mock_check_auth):
        self._auth_ok(mock_check_auth)
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.whirlpool_provider,
            credentials=[{"id": "client_id", "type": "PASSWORD", "label": "Client ID", "value": "cid"}],
            is_active=True,
        )
        self.project.manager_agent = self.whirlpool_manager
        self.project.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["current"])
        vendors = [item.get("label") for item in body["providers"]]
        self.assertNotIn("Whirlpool", vendors)
        self.assertIn("OpenAI", vendors)

    @patch("nexus.inline_agents.api.views.notify_async")
    @patch("nexus.projects.permissions._check_project_authorization")
    def test_post_cannot_activate_whirlpool(self, mock_check_auth, mock_notify_async):
        self._auth_ok(mock_check_auth)
        response = self.client.post(
            self.url,
            {
                "provider_uuid": str(self.whirlpool_provider.uuid),
                "credentials": [{"id": "client_id", "value": "cid"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            ProjectModelProvider.objects.filter(project=self.project, provider=self.whirlpool_provider).exists()
        )
        mock_notify_async.assert_not_called()

    @patch("nexus.inline_agents.api.views.notify_async")
    @patch("nexus.projects.permissions._check_project_authorization")
    def test_post_cannot_replace_active_whirlpool(self, mock_check_auth, mock_notify_async):
        self._auth_ok(mock_check_auth)
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.whirlpool_provider,
            credentials=[{"id": "client_id", "type": "PASSWORD", "label": "Client ID", "value": "cid"}],
            is_active=True,
        )
        self.project.manager_agent = self.whirlpool_manager
        self.project.save()

        response = self.client.post(
            self.url,
            {
                "provider_uuid": str(self.openai_provider.uuid),
                "credentials": [{"id": "api_key", "value": "sk-test"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        pmp = ProjectModelProvider.objects.get(project=self.project, provider=self.whirlpool_provider)
        self.assertTrue(pmp.is_active)
        self.project.refresh_from_db()
        self.assertEqual(self.project.manager_agent_id, self.whirlpool_manager.id)
        mock_notify_async.assert_not_called()

    @patch("nexus.inline_agents.api.views.notify_async")
    @patch("nexus.projects.permissions._check_project_authorization")
    def test_delete_cannot_deactivate_whirlpool(self, mock_check_auth, mock_notify_async):
        self._auth_ok(mock_check_auth)
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.whirlpool_provider,
            credentials=[{"id": "client_id", "type": "PASSWORD", "label": "Client ID", "value": "cid"}],
            is_active=True,
        )
        self.project.manager_agent = self.whirlpool_manager
        self.project.save()

        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 403)
        pmp = ProjectModelProvider.objects.get(project=self.project, provider=self.whirlpool_provider)
        self.assertTrue(pmp.is_active)
        mock_notify_async.assert_not_called()

    @patch("nexus.projects.permissions._check_project_authorization")
    def test_engine_source_stays_standard_for_whirlpool(self, mock_check_auth):
        self._auth_ok(mock_check_auth)
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.whirlpool_provider,
            credentials=[{"id": "client_id", "type": "PASSWORD", "label": "Client ID", "value": "cid"}],
            is_active=True,
        )
        response = self.client.get(self.engine_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["engine_source"], "STANDARD")

    @patch("nexus.inline_agents.api.views.notify_async")
    @patch("nexus.projects.permissions._check_project_authorization")
    def test_managers_api_cannot_assign_or_leave_whirlpool(self, mock_check_auth, mock_notify_async):
        self._auth_ok(mock_check_auth)
        response = self.client.post(
            self.managers_url, {"currentManager": str(self.whirlpool_manager.uuid)}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        self.project.refresh_from_db()
        self.assertIsNone(self.project.manager_agent)

        self.project.manager_agent = self.whirlpool_manager
        self.project.save()
        response = self.client.post(
            self.managers_url, {"currentManager": str(self.openai_manager.uuid)}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        self.project.refresh_from_db()
        self.assertEqual(self.project.manager_agent_id, self.whirlpool_manager.id)

        response = self.client.get(self.managers_url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotEqual(body.get("currentManager"), str(self.whirlpool_manager.uuid))
        if "new" in body:
            self.assertNotEqual(body["new"].get("id"), str(self.whirlpool_manager.uuid))
        mock_notify_async.assert_not_called()
