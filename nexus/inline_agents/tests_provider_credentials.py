from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from django.utils import timezone

from nexus.agents.encryption import encrypt_value
from nexus.inline_agents.api.views import _sync_provider_credentials_on_manager_change
from nexus.inline_agents.backends.openai.models import (
    ManagerAgent,
    ModelProvider,
    ProjectModelProvider,
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


def _create_provider(model_vendor="openai"):
    schema_map = {
        "openai": {
            "label": "OpenAI",
            "credentials": [
                {"id": "api_key", "label": "API key", "type": "PASSWORD"},
                {"id": "api_base", "label": "API base URL", "type": "TEXT"},
            ],
            "models": ["gpt-4o", "gpt-4o-mini"],
        },
        "gemini": {
            "label": "Google Gemini",
            "credentials": [
                {"id": "api_key", "label": "API key", "type": "PASSWORD"},
            ],
            "models": ["gemini-2.5-pro"],
        },
        "vertex_ai": {
            "label": "Vertex AI",
            "credentials": [
                {"id": "service_account_json", "label": "Service account JSON", "type": "TEXTAREA"},
            ],
            "models": ["gemini-2.5-pro"],
        },
    }
    data = schema_map[model_vendor]
    return ModelProvider.objects.create(
        model_vendor=model_vendor,
        label=data["label"],
        credentials=data["credentials"],
        models=data["models"],
    )


@override_settings(CREDENTIAL_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY)
class TestProjectModelProviderEncryption(TestCase):
    def setUp(self):
        self.project = ProjectFactory(name="EncryptProject")
        self.provider = _create_provider("openai")

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
        provider = _create_provider("vertex_ai")
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


class TestSyncProviderCredentialsOnManagerChange(TestCase):
    def setUp(self):
        self.project = ProjectFactory(name="SyncProject")
        self.openai_provider = _create_provider("openai")
        self.gemini_provider = _create_provider("gemini")
        self.openai_manager = _create_manager(model_vendor="openai")
        self.gemini_manager = _create_manager(model_vendor="gemini")

    def test_deactivates_on_vendor_change(self):
        pmp = ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.openai_provider,
            credentials=[{"id": "api_key", "type": "PASSWORD", "label": "API key", "value": "sk-test"}],
            is_active=True,
        )

        _sync_provider_credentials_on_manager_change(self.project, self.gemini_manager)

        pmp.refresh_from_db()
        self.assertFalse(pmp.is_active)

    def test_reactivates_when_vendor_returns(self):
        pmp = ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.openai_provider,
            credentials=[{"id": "api_key", "type": "PASSWORD", "label": "API key", "value": "sk-test"}],
            is_active=False,
        )

        _sync_provider_credentials_on_manager_change(self.project, self.openai_manager)

        pmp.refresh_from_db()
        self.assertTrue(pmp.is_active)

    def test_deactivates_all_when_no_manager(self):
        pmp = ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.openai_provider,
            credentials=[{"id": "api_key", "type": "PASSWORD", "label": "API key", "value": "sk-test"}],
            is_active=True,
        )

        _sync_provider_credentials_on_manager_change(self.project, None)

        pmp.refresh_from_db()
        self.assertFalse(pmp.is_active)

    def test_keeps_active_when_same_vendor(self):
        pmp = ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.openai_provider,
            credentials=[{"id": "api_key", "type": "PASSWORD", "label": "API key", "value": "sk-test"}],
            is_active=True,
        )
        another_openai_manager = _create_manager(model_vendor="openai", name="OpenAI v2")

        _sync_provider_credentials_on_manager_change(self.project, another_openai_manager)

        pmp.refresh_from_db()
        self.assertTrue(pmp.is_active)


@override_settings(CREDENTIAL_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY)
class TestManagerAgentRepositoryProjectCredentials(TestCase):
    def setUp(self):
        self.project = ProjectFactory(name="RepoTestProject")
        self.manager = _create_manager(model_vendor="openai")
        self.project.manager_agent = self.manager
        self.project.save()
        self.provider = _create_provider("openai")

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
        self.provider = _create_provider("openai")

    def test_standard_when_no_credentials(self):
        has_own = (
            ProjectModelProvider.objects.filter(
                project=self.project,
                provider__model_vendor=self.manager.model_vendor,
                is_active=True,
            )
            .exclude(credentials=[])
            .exists()
        )
        self.assertFalse(has_own)

    def test_own_when_active_credentials(self):
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.provider,
            credentials=[
                {"id": "api_key", "type": "PASSWORD", "label": "API key", "value": "sk-test"},
            ],
            is_active=True,
        )
        has_own = (
            ProjectModelProvider.objects.filter(
                project=self.project,
                provider__model_vendor=self.manager.model_vendor,
                is_active=True,
            )
            .exclude(credentials=[])
            .exists()
        )
        self.assertTrue(has_own)

    def test_standard_when_inactive_credentials(self):
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=self.provider,
            credentials=[
                {"id": "api_key", "type": "PASSWORD", "label": "API key", "value": "sk-test"},
            ],
            is_active=False,
        )
        has_own = (
            ProjectModelProvider.objects.filter(
                project=self.project,
                provider__model_vendor=self.manager.model_vendor,
                is_active=True,
            )
            .exclude(credentials=[])
            .exists()
        )
        self.assertFalse(has_own)

    def test_standard_when_different_vendor(self):
        gemini_provider = _create_provider("gemini")
        ProjectModelProvider.objects.create(
            project=self.project,
            provider=gemini_provider,
            credentials=[
                {"id": "api_key", "type": "PASSWORD", "label": "API key", "value": "gem-key"},
            ],
            is_active=True,
        )
        has_own = (
            ProjectModelProvider.objects.filter(
                project=self.project,
                provider__model_vendor=self.manager.model_vendor,
                is_active=True,
            )
            .exclude(credentials=[])
            .exists()
        )
        self.assertFalse(has_own)


@override_settings(CREDENTIAL_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY)
class TestVertexAICredentialInjection(TestCase):
    def setUp(self):
        self.project = ProjectFactory(name="VertexProject")
        self.manager = _create_manager(model_vendor="vertex_ai")
        self.project.manager_agent = self.manager
        self.project.save()
        self.provider = _create_provider("vertex_ai")

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

        openai_provider = _create_provider("openai")
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
