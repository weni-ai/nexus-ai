from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase, override_settings

from router.services.manager_pipeline_version import (
    is_legacy_manager_uuid,
    manager_pipeline_version_from_project,
)
from router.tasks.invocation_context import CachedProjectData

LEGACY_UUID = "21b405a4-b5a5-4cf5-bb5f-efce2620e834"
NEW_UUID = "65f8c6d7-7518-483d-a8f1-5b8e4132fb0a"


@override_settings(LEGACY_MANAGER_AGENT_UUIDS=[LEGACY_UUID])
class TestManagerPipelineVersionFromProject(SimpleTestCase):
    def test_none_when_no_manager_agent(self):
        project = SimpleNamespace(manager_agent=None)
        self.assertIsNone(manager_pipeline_version_from_project(project))

    def test_legacy_uuid_returns_legacy_token(self):
        agent = SimpleNamespace(uuid=LEGACY_UUID)
        project = SimpleNamespace(manager_agent=agent)
        self.assertEqual(manager_pipeline_version_from_project(project), "2.6")

    def test_new_uuid_returns_none(self):
        agent = SimpleNamespace(uuid=NEW_UUID)
        project = SimpleNamespace(manager_agent=agent)
        self.assertIsNone(manager_pipeline_version_from_project(project))

    def test_uuid_match_is_case_insensitive_and_trims(self):
        agent = SimpleNamespace(uuid=f"  {LEGACY_UUID.upper()}  ")
        project = SimpleNamespace(manager_agent=agent)
        self.assertEqual(manager_pipeline_version_from_project(project), "2.6")

    def test_admin_editable_extra_args_is_ignored(self):
        agent = SimpleNamespace(
            uuid=NEW_UUID,
            manager_extra_args={"pipeline_version": "2.6"},
        )
        project = SimpleNamespace(manager_agent=agent)
        self.assertIsNone(manager_pipeline_version_from_project(project))


@override_settings(LEGACY_MANAGER_AGENT_UUIDS=[LEGACY_UUID])
class TestIsLegacyManagerUuid(SimpleTestCase):
    def test_none_is_not_legacy(self):
        self.assertFalse(is_legacy_manager_uuid(None))

    def test_listed_uuid_is_legacy(self):
        self.assertTrue(is_legacy_manager_uuid(LEGACY_UUID))

    def test_unlisted_uuid_is_not_legacy(self):
        self.assertFalse(is_legacy_manager_uuid(NEW_UUID))

    @override_settings(LEGACY_MANAGER_AGENT_UUIDS=[])
    def test_empty_setting_means_no_legacy(self):
        self.assertFalse(is_legacy_manager_uuid(LEGACY_UUID))


class TestCachedProjectDataEdgeCases(TestCase):
    def test_formatter_config_always_dict_even_when_not_configured(self):
        result = CachedProjectData.from_pre_generation_data(
            project_dict={
                "uuid": "test-uuid",
                "use_components": True,
                "default_formatter_foundation_model": None,
                "formatter_instructions": None,
            },
            content_base_dict={"uuid": "cb-uuid"},
            team=[],
            guardrails_config={},
            inline_agent_config_dict=None,
            instructions=[],
            agent_data=None,
        )

        self.assertIsNotNone(result.formatter_agent_configurations)
        self.assertIsInstance(result.formatter_agent_configurations, dict)

        expected_keys = [
            "formatter_foundation_model",
            "formatter_instructions",
            "formatter_reasoning_effort",
            "formatter_reasoning_summary",
            "formatter_send_only_assistant_message",
            "formatter_tools_descriptions",
        ]
        for key in expected_keys:
            self.assertIn(key, result.formatter_agent_configurations)

    def test_formatter_config_created_when_model_provided(self):
        result = CachedProjectData.from_pre_generation_data(
            project_dict={
                "uuid": "test-uuid",
                "use_components": True,
                "default_formatter_foundation_model": "gpt-4",
                "formatter_instructions": None,
            },
            content_base_dict={"uuid": "cb-uuid"},
            team=[],
            guardrails_config={},
            inline_agent_config_dict=None,
            instructions=[],
            agent_data=None,
        )

        self.assertIsNotNone(result.formatter_agent_configurations)
        self.assertEqual(result.formatter_agent_configurations.get("formatter_foundation_model"), "gpt-4")

    def test_formatter_config_created_when_instructions_provided(self):
        result = CachedProjectData.from_pre_generation_data(
            project_dict={
                "uuid": "test-uuid",
                "use_components": True,
                "default_formatter_foundation_model": None,
                "formatter_instructions": "Custom formatting instructions",
            },
            content_base_dict={"uuid": "cb-uuid"},
            team=[],
            guardrails_config={},
            inline_agent_config_dict=None,
            instructions=[],
            agent_data=None,
        )

        self.assertIsNotNone(result.formatter_agent_configurations)
        self.assertEqual(
            result.formatter_agent_configurations.get("formatter_instructions"), "Custom formatting instructions"
        )

    def test_agent_data_none_passed_through(self):
        result = CachedProjectData.from_pre_generation_data(
            project_dict={"uuid": "test-uuid"},
            content_base_dict={"uuid": "cb-uuid"},
            team=[],
            guardrails_config={},
            inline_agent_config_dict=None,
            instructions=[],
            agent_data=None,
        )

        self.assertIsNone(result.agent_data)

    def test_agent_data_dict_passed_through(self):
        agent_data = {
            "name": "Test Agent",
            "role": "Assistant",
            "goal": "Help users",
            "personality": "Friendly",
        }

        result = CachedProjectData.from_pre_generation_data(
            project_dict={"uuid": "test-uuid"},
            content_base_dict={"uuid": "cb-uuid"},
            team=[],
            guardrails_config={},
            inline_agent_config_dict=None,
            instructions=[],
            agent_data=agent_data,
        )

        self.assertEqual(result.agent_data, agent_data)

    def test_get_invoke_kwargs_includes_formatter_dict(self):
        cached_data = CachedProjectData(
            project_dict={"use_components": True},
            content_base_dict={"uuid": "cb-uuid"},
            team=[],
            guardrails_config={},
            inline_agent_config_dict=None,
            instructions=[],
            agent_data=None,
            formatter_agent_configurations={
                "formatter_foundation_model": None,
                "formatter_instructions": None,
            },
        )

        kwargs = cached_data.get_invoke_kwargs(team=[])

        self.assertIn("formatter_agent_configurations", kwargs)
        self.assertIsInstance(kwargs["formatter_agent_configurations"], dict)

    def test_get_invoke_kwargs_with_none_agent_data(self):
        cached_data = CachedProjectData(
            project_dict={},
            content_base_dict={"uuid": "cb-uuid"},
            team=[],
            guardrails_config={},
            inline_agent_config_dict=None,
            instructions=[],
            agent_data=None,
            formatter_agent_configurations=None,
        )

        kwargs = cached_data.get_invoke_kwargs(team=[])

        self.assertIn("agent_data", kwargs)
        self.assertIsNone(kwargs["agent_data"])

    def test_get_invoke_kwargs_with_all_values(self):
        cached_data = CachedProjectData(
            project_dict={
                "use_components": True,
                "rationale_switch": True,
                "use_prompt_creation_configurations": False,
                "conversation_turns_to_include": 20,
                "exclude_previous_thinking_steps": False,
                "human_support": True,
                "default_supervisor_foundation_model": "gpt-4",
                "human_support_prompt": "Business rules here",
            },
            content_base_dict={"uuid": "cb-uuid-123"},
            team=[{"name": "agent1"}],
            guardrails_config={"guardrailIdentifier": "guard1"},
            inline_agent_config_dict={"default_instructions_for_collaborators": "Be helpful"},
            instructions=["Instruction 1", "Instruction 2"],
            agent_data={"name": "Test Agent"},
            formatter_agent_configurations={"formatter_foundation_model": "gpt-4"},
        )

        kwargs = cached_data.get_invoke_kwargs(team=[{"name": "agent1"}])

        expected_keys = [
            "team",
            "use_components",
            "rationale_switch",
            "use_prompt_creation_configurations",
            "conversation_turns_to_include",
            "exclude_previous_thinking_steps",
            "human_support",
            "default_supervisor_foundation_model",
            "content_base_uuid",
            "business_rules",
            "instructions",
            "agent_data",
            "formatter_agent_configurations",
            "guardrails_config",
            "default_instructions_for_collaborators",
        ]

        for key in expected_keys:
            self.assertIn(key, kwargs)

        self.assertTrue(kwargs["use_components"])
        self.assertEqual(kwargs["conversation_turns_to_include"], 20)
        self.assertEqual(kwargs["agent_data"], {"name": "Test Agent"})

    def test_get_invoke_kwargs_default_values(self):
        cached_data = CachedProjectData(
            project_dict={},
            content_base_dict={"uuid": "cb-uuid"},
            team=[],
            guardrails_config={},
            inline_agent_config_dict=None,
            instructions=[],
            agent_data=None,
            formatter_agent_configurations=None,
        )

        kwargs = cached_data.get_invoke_kwargs(team=[])

        self.assertFalse(kwargs.get("use_components", True))
        self.assertFalse(kwargs.get("rationale_switch", True))
        self.assertEqual(kwargs.get("conversation_turns_to_include"), 10)
        self.assertTrue(kwargs.get("exclude_previous_thinking_steps", False))

    def test_get_invoke_kwargs_includes_manager_pipeline_version(self):
        cached_data = CachedProjectData(
            project_dict={"manager_pipeline_version": "2.6"},
            content_base_dict={"uuid": "cb-uuid"},
            team=[],
            guardrails_config={},
            inline_agent_config_dict=None,
            instructions=[],
            agent_data=None,
            formatter_agent_configurations={},
        )

        kwargs = cached_data.get_invoke_kwargs(team=[])

        self.assertEqual(kwargs.get("manager_pipeline_version"), "2.6")

    def test_get_invoke_kwargs_manager_pipeline_version_defaults_none(self):
        cached_data = CachedProjectData(
            project_dict={},
            content_base_dict={"uuid": "cb-uuid"},
            team=[],
            guardrails_config={},
            inline_agent_config_dict=None,
            instructions=[],
            agent_data=None,
            formatter_agent_configurations={},
        )

        kwargs = cached_data.get_invoke_kwargs(team=[])

        self.assertIsNone(kwargs.get("manager_pipeline_version"))
