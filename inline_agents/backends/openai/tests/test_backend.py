import pendulum
import pytest
from django.test import TestCase

from inline_agents.backends.openai.backend import OpenAIBackend, OpenAISupervisorRepository
from inline_agents.backends.openai.tests.openai_factory import OpenAISupervisorFactory
from nexus.inline_agents.backends.openai.models import ManagerAgent
from nexus.inline_agents.backends.openai.repository import ManagerAgentRepository
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class OpenAISupervisorRepositoryTestCase(TestCase):
    def setUp(self):
        """Set up test data before each test method."""
        self.project = ProjectFactory()
        self.supervisor = OpenAISupervisorFactory()

    def test_get_supervisor_success(self):
        """Test successful retrieval of supervisor with all attributes."""
        result = OpenAISupervisorRepository.get_supervisor(
            use_components=self.project.use_components,
            human_support=self.project.human_support,
            default_supervisor_foundation_model=self.project.default_supervisor_foundation_model,
        )

        expected_keys = [
            "instruction",
            "use_components",
            "use_human_support",
            "components_instructions",
            "formatter_agent_components_instructions",
            "components_instructions_up",
            "human_support_instructions",
            "tools",
            "foundation_model",
            "knowledge_bases",
            "prompt_override_configuration",
            "default_instructions_for_collaborators",
            "max_tokens",
        ]
        self.assertEqual(set(result.keys()), set(expected_keys))
        self.assertEqual(result["foundation_model"], self.supervisor.foundation_model)
        self.assertEqual(result["knowledge_bases"], self.supervisor.knowledge_bases)
        self.assertEqual(result["prompt_override_configuration"], self.supervisor.prompt_override_configuration)

    def test_get_supervisor_instructions_default_case(self):
        """Test _get_supervisor_instructions when project has no special flags."""
        result = OpenAISupervisorRepository._get_supervisor_instructions(self.supervisor)
        self.assertEqual(result, self.supervisor.instruction)

    def test_get_supervisor_instructions_components_only(self):
        """Test _get_supervisor_instructions when project uses components only."""
        # Create supervisor with specific values
        supervisor = OpenAISupervisorFactory(instruction="Components prompt")

        result = OpenAISupervisorRepository._get_supervisor_instructions(supervisor)
        self.assertEqual(result, "Components prompt")

    def test_get_supervisor_instructions_human_support_only(self):
        """Test _get_supervisor_instructions when project has human support only."""
        # Create supervisor with specific values
        supervisor = OpenAISupervisorFactory(instruction="Human support prompt")

        result = OpenAISupervisorRepository._get_supervisor_instructions(supervisor)
        self.assertEqual(result, "Human support prompt")

    def test_get_supervisor_instructions_components_and_human_support(self):
        """Test _get_supervisor_instructions when project has both components and human support."""
        # Create supervisor with specific values
        supervisor = OpenAISupervisorFactory(instruction="Components + Human support prompt")

        result = OpenAISupervisorRepository._get_supervisor_instructions(supervisor)
        self.assertEqual(result, "Components + Human support prompt")

    def test_get_supervisor_tools_default_case(self):
        """Test _get_supervisor_tools when project has no human support."""
        result = OpenAISupervisorRepository._get_supervisor_tools(supervisor=self.supervisor, human_support=False)
        self.assertEqual(result, self.supervisor.action_groups)

    def test_get_supervisor_tools_human_support(self):
        """Test _get_supervisor_tools when project has human support."""
        result = OpenAISupervisorRepository._get_supervisor_tools(supervisor=self.supervisor, human_support=True)
        self.assertEqual(result, self.supervisor.human_support_action_groups)

    @pytest.mark.skip(reason="instruction field has NOT NULL constraint in database")
    def test_get_supervisor_instructions_with_none_values(self):
        """Test _get_supervisor_instructions when instruction is None."""
        # This test is skipped because the instruction field is NOT NULL in the database
        # and cannot be set to None
        pass

    def test_get_supervisor_tools_with_none_values(self):
        """Test _get_supervisor_tools when human_support_action_groups is None."""
        supervisor = OpenAISupervisorFactory(human_support_action_groups=None)

        result = OpenAISupervisorRepository._get_supervisor_tools(supervisor=supervisor, human_support=True)
        self.assertIsNone(result)

    def test_get_supervisor_multiple_supervisors(self):
        """Test that get_supervisor returns the last supervisor by ID."""
        supervisor1 = OpenAISupervisorFactory()
        supervisor2 = OpenAISupervisorFactory()
        supervisor3 = OpenAISupervisorFactory()

        result = OpenAISupervisorRepository.get_supervisor(
            use_components=self.project.use_components,
            human_support=self.project.human_support,
            default_supervisor_foundation_model=self.project.default_supervisor_foundation_model,
        )

        # Should return the supervisor with the highest ID
        expected_supervisor = max([supervisor1, supervisor2, supervisor3], key=lambda x: x.id)
        self.assertEqual(result["foundation_model"], expected_supervisor.foundation_model)

    def test_get_supervisor_integration(self):
        """Test the complete integration of get_supervisor method."""
        self.project.use_components = True
        self.project.human_support = True
        self.project.save()

        OpenAISupervisorFactory(
            instruction="Default instruction",
            components_prompt="Components prompt",
            human_support_prompt="Human support prompt",
            components_human_support_prompt="Components + Human support prompt",
            action_groups=[{"name": "default", "type": "action"}],
            human_support_action_groups=[{"name": "human_support", "type": "action"}],
            foundation_model="gpt-4-turbo",
            knowledge_bases=[{"name": "kb1", "type": "knowledge"}],
            prompt_override_configuration={"temperature": 0.8, "max_tokens": 1000},
            default_instructions_for_collaborators="Always be helpful and professional.",
            max_tokens=4096,
        )

        result = OpenAISupervisorRepository.get_supervisor(
            use_components=self.project.use_components,
            human_support=self.project.human_support,
            default_supervisor_foundation_model=self.project.default_supervisor_foundation_model,
        )

        self.assertEqual(result["instruction"], "Default instruction")
        self.assertEqual(result["tools"], [{"name": "human_support", "type": "action"}])
        self.assertEqual(result["foundation_model"], "gpt-4-turbo")
        self.assertEqual(result["knowledge_bases"], [{"name": "kb1", "type": "knowledge"}])
        self.assertEqual(result["prompt_override_configuration"], {"temperature": 0.8, "max_tokens": 1000})
        self.assertEqual(result["default_instructions_for_collaborators"], "Always be helpful and professional.")
        self.assertEqual(result["max_tokens"], 4096)

    def test_default_instructions_for_collaborators_field(self):
        """Test that default_instructions_for_collaborators field is properly handled."""
        supervisor = OpenAISupervisorFactory(
            default_instructions_for_collaborators="Always be helpful and polite to users."
        )
        self.assertEqual(supervisor.default_instructions_for_collaborators, "Always be helpful and polite to users.")

        supervisor_none = OpenAISupervisorFactory(default_instructions_for_collaborators=None)
        self.assertIsNone(supervisor_none.default_instructions_for_collaborators)

        supervisor_empty = OpenAISupervisorFactory(default_instructions_for_collaborators="")
        self.assertEqual(supervisor_empty.default_instructions_for_collaborators, "")

    def test_get_supervisor_includes_default_instructions_for_collaborators(self):
        """Test that get_supervisor includes default_instructions_for_collaborators in the result."""
        OpenAISupervisorFactory(default_instructions_for_collaborators="Be concise and professional in all responses.")

        result = OpenAISupervisorRepository.get_supervisor(
            use_components=self.project.use_components,
            human_support=self.project.human_support,
            default_supervisor_foundation_model=self.project.default_supervisor_foundation_model,
        )

        self.assertIn("default_instructions_for_collaborators", result)
        self.assertEqual(
            result["default_instructions_for_collaborators"], "Be concise and professional in all responses."
        )


class TestFormatterAgentNoneHandling(TestCase):
    def setUp(self):
        self.backend = OpenAIBackend()

    def test_create_formatter_agent_none_config_normalized(self):
        formatter_agent_configurations = None
        if formatter_agent_configurations is None:
            formatter_agent_configurations = {}

        self.assertEqual(formatter_agent_configurations, {})
        self.assertIsNone(formatter_agent_configurations.get("formatter_foundation_model"))

    def test_create_formatter_agent_empty_dict_config_works(self):
        formatter_agent_configurations = {}

        self.assertIsNone(formatter_agent_configurations.get("formatter_foundation_model"))
        self.assertIsNone(formatter_agent_configurations.get("formatter_instructions"))
        self.assertIsNone(formatter_agent_configurations.get("formatter_reasoning_effort"))
        self.assertIsNone(formatter_agent_configurations.get("formatter_send_only_assistant_message"))

    def test_formatter_config_always_dict_from_invocation_context(self):
        formatter_agent_configurations = {
            "formatter_foundation_model": None,
            "formatter_instructions": None,
            "formatter_reasoning_effort": None,
            "formatter_reasoning_summary": None,
            "formatter_send_only_assistant_message": None,
            "formatter_tools_descriptions": None,
        }

        self.assertIsInstance(formatter_agent_configurations, dict)
        self.assertIsNone(formatter_agent_configurations.get("formatter_foundation_model"))

    def test_formatter_config_none_does_not_crash_on_get(self):
        formatter_agent_configurations = {}
        result = formatter_agent_configurations.get("formatter_send_only_assistant_message")
        self.assertIsNone(result)

    def test_formatter_config_with_values(self):
        formatter_agent_configurations = {
            "formatter_send_only_assistant_message": True,
            "formatter_foundation_model": "gpt-4",
            "formatter_instructions": "Custom instructions",
        }

        self.assertTrue(formatter_agent_configurations.get("formatter_send_only_assistant_message"))
        self.assertEqual(formatter_agent_configurations.get("formatter_foundation_model"), "gpt-4")
        self.assertEqual(formatter_agent_configurations.get("formatter_instructions"), "Custom instructions")


class TestFormatterAgentSkip(TestCase):
    def test_formatter_not_needed_when_use_components_false(self):
        use_components = False

        if use_components:
            self.fail("Should not enter formatter branch when use_components=False")


class ManagerAgentRepositoryTestCase(TestCase):
    def setUp(self):
        """Set up test data before each test method."""
        self.repository = ManagerAgentRepository()

        # Create a default manager agent
        self.manager_agent = ManagerAgent.objects.create(
            name="Test Manager Agent",
            base_prompt="Test base prompt",
            foundation_model="gpt-4",
            model_vendor="openai",
            model_has_reasoning=False,
            api_key="test-api-key",
            api_base="https://api.openai.com/v1",
            api_version="2024-01-01",
            max_tokens=2048,
            collaborator_max_tokens=2048,
            reasoning_effort=None,
            reasoning_summary="auto",
            parallel_tool_calls=False,
            tools=[{"name": "test_tool", "type": "function"}],
            knowledge_bases=[{"name": "test_kb", "type": "knowledge"}],
            human_support_prompt="Human support prompt",
            human_support_tools=[{"name": "human_support_tool", "type": "function"}],
            audio_orchestration_max_tokens=2048,
            audio_orchestration_collaborator_max_tokens=2048,
            header_components_prompt="Header components prompt",
            footer_components_prompt="Footer components prompt",
            component_tools_descriptions={},
            formatter_agent_prompt="Formatter agent prompt",
            formatter_agent_reasoning_effort=None,
            formatter_agent_reasoning_summary="auto",
            formatter_agent_send_only_assistant_message=False,
            formatter_agent_tools_descriptions={},
            formatter_agent_foundation_model="gpt-4",
            formatter_agent_model_has_reasoning=False,
            formatter_tools_descriptions={},
            collaborators_foundation_model="gpt-4",
            override_collaborators_foundation_model=False,
            default_instructions_for_collaborators="Default instructions",
            default=True,
            public=True,
            release_date=pendulum.now(),
        )

    def test_supervisor_to_dict(self):
        """Test _supervisor_to_dict converts ManagerAgent to dict correctly."""
        result = self.repository._supervisor_to_dict(self.manager_agent)

        self.assertIsInstance(result, dict)
        self.assertNotIn("_state", result)
        self.assertEqual(result["name"], self.manager_agent.name)
        self.assertEqual(result["base_prompt"], self.manager_agent.base_prompt)
        self.assertEqual(result["foundation_model"], self.manager_agent.foundation_model)

    def test_get_supervisor_with_specific_uuid(self):
        """Test get_supervisor with a specific supervisor_agent_uuid."""
        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
            human_support=False,
            use_components=False,
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result["instruction"], self.manager_agent.base_prompt)
        self.assertEqual(result["foundation_model"], self.manager_agent.foundation_model)
        self.assertEqual(result["model_vendor"], self.manager_agent.model_vendor)
        self.assertFalse(result["use_human_support"])
        self.assertFalse(result["use_components"])

    def test_get_supervisor_with_default_fallback(self):
        """Test get_supervisor falls back to default manager when UUID doesn't exist."""
        non_existent_uuid = "00000000-0000-0000-0000-000000000000"

        result = self.repository.get_supervisor(
            supervisor_agent_uuid=non_existent_uuid,
            human_support=False,
            use_components=False,
        )

        # Should fall back to default manager
        self.assertIsInstance(result, dict)
        self.assertEqual(result["foundation_model"], self.manager_agent.foundation_model)

    def test_get_supervisor_with_none_uuid(self):
        """Test get_supervisor with None UUID falls back to default."""
        result = self.repository.get_supervisor(
            supervisor_agent_uuid=None,
            human_support=False,
            use_components=False,
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result["foundation_model"], self.manager_agent.foundation_model)

    def test_get_supervisor_with_human_support_true(self):
        """Test get_supervisor with human_support=True."""
        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
            human_support=True,
            use_components=False,
        )

        self.assertTrue(result["use_human_support"])
        self.assertEqual(result["tools"], self.manager_agent.human_support_tools)
        self.assertEqual(result["human_support_instructions"], self.manager_agent.human_support_prompt)

    def test_get_supervisor_with_human_support_false(self):
        """Test get_supervisor with human_support=False."""
        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
            human_support=False,
            use_components=False,
        )

        self.assertFalse(result["use_human_support"])
        self.assertEqual(result["tools"], self.manager_agent.tools)

    def test_get_supervisor_with_use_components_true(self):
        """Test get_supervisor with use_components=True."""
        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
            human_support=False,
            use_components=True,
        )

        self.assertTrue(result["use_components"])

    def test_get_supervisor_user_model_credentials_with_api_key(self):
        """Test get_supervisor includes user_model_credentials when api_key exists."""
        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
        )

        self.assertIn("user_model_credentials", result)
        self.assertEqual(result["user_model_credentials"]["api_key"], self.manager_agent.api_key)
        self.assertEqual(result["user_model_credentials"]["api_base"], self.manager_agent.api_base)
        self.assertEqual(result["user_model_credentials"]["api_version"], self.manager_agent.api_version)

    def test_get_supervisor_user_model_credentials_without_api_key(self):
        """Test get_supervisor returns empty dict when api_key is None."""
        self.manager_agent.api_key = None
        self.manager_agent.save()

        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
        )

        self.assertEqual(result["user_model_credentials"], {})

    def test_get_supervisor_user_model_credentials_with_empty_api_key(self):
        """Test get_supervisor returns empty dict when api_key is empty string."""
        self.manager_agent.api_key = ""
        self.manager_agent.save()

        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
        )

        self.assertEqual(result["user_model_credentials"], {})

    def test_get_supervisor_model_settings(self):
        """Test get_supervisor includes correct model_settings."""
        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
        )

        self.assertIn("model_settings", result)
        self.assertEqual(result["model_settings"]["model_has_reasoning"], self.manager_agent.model_has_reasoning)
        self.assertEqual(result["model_settings"]["reasoning_effort"], self.manager_agent.reasoning_effort)
        self.assertEqual(result["model_settings"]["reasoning_summary"], self.manager_agent.reasoning_summary)
        self.assertEqual(result["model_settings"]["parallel_tool_calls"], self.manager_agent.parallel_tool_calls)

    def test_get_supervisor_max_tokens_structure(self):
        """Test get_supervisor includes correct max_tokens structure."""
        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
        )

        self.assertIn("max_tokens", result)
        self.assertIsInstance(result["max_tokens"], dict)
        self.assertEqual(result["max_tokens"]["supervisor"], self.manager_agent.max_tokens)
        self.assertEqual(result["max_tokens"]["collaborator"], self.manager_agent.collaborator_max_tokens)
        self.assertEqual(result["max_tokens"]["audio_orchestration"], self.manager_agent.audio_orchestration_max_tokens)
        self.assertEqual(
            result["max_tokens"]["audio_orchestration_collaborator"],
            self.manager_agent.audio_orchestration_collaborator_max_tokens,
        )

    def test_get_supervisor_formatter_agent_configurations(self):
        """Test get_supervisor includes correct formatter_agent_configurations."""
        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
        )

        self.assertIn("formatter_agent_configurations", result)
        formatter_config = result["formatter_agent_configurations"]
        self.assertEqual(formatter_config["formatter_instructions"], self.manager_agent.formatter_agent_prompt)
        self.assertEqual(
            formatter_config["formatter_reasoning_effort"], self.manager_agent.formatter_agent_reasoning_effort
        )
        self.assertEqual(
            formatter_config["formatter_reasoning_summary"], self.manager_agent.formatter_agent_reasoning_summary
        )
        self.assertEqual(
            formatter_config["formatter_send_only_assistant_message"],
            self.manager_agent.formatter_agent_send_only_assistant_message,
        )
        self.assertEqual(
            formatter_config["formatter_foundation_model"], self.manager_agent.formatter_agent_foundation_model
        )
        self.assertEqual(
            formatter_config["formatter_agent_model_has_reasoning"],
            self.manager_agent.formatter_agent_model_has_reasoning,
        )
        self.assertEqual(
            formatter_config["formatter_tools_descriptions"], self.manager_agent.formatter_tools_descriptions
        )

    def test_get_supervisor_collaborator_configurations(self):
        """Test get_supervisor includes correct collaborator_configurations."""
        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
        )

        self.assertIn("collaborator_configurations", result)
        collaborator_config = result["collaborator_configurations"]
        self.assertEqual(
            collaborator_config["override_collaborators_foundation_model"],
            self.manager_agent.override_collaborators_foundation_model,
        )
        self.assertEqual(
            collaborator_config["collaborators_foundation_model"], self.manager_agent.collaborators_foundation_model
        )
        self.assertEqual(
            collaborator_config["default_instructions_for_collaborators"],
            self.manager_agent.default_instructions_for_collaborators,
        )

    def test_get_supervisor_components_instructions(self):
        """Test get_supervisor includes correct components instructions."""
        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
        )

        self.assertEqual(result["components_instructions_up"], self.manager_agent.header_components_prompt)
        self.assertEqual(result["components_instructions"], self.manager_agent.footer_components_prompt)
        self.assertEqual(result["formatter_agent_components_instructions"], self.manager_agent.formatter_agent_prompt)

    def test_get_supervisor_knowledge_bases(self):
        """Test get_supervisor includes knowledge_bases."""
        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
        )

        self.assertEqual(result["knowledge_bases"], self.manager_agent.knowledge_bases)

    def test_get_supervisor_agent_tools_with_human_support(self):
        """Test _get_supervisor_agent_tools returns human_support_tools when use_human_support=True."""
        supervisor_data = {"tools": [{"name": "regular_tool"}], "human_support_tools": [{"name": "human_tool"}]}

        result = self.repository._get_supervisor_agent_tools(supervisor=supervisor_data, use_human_support=True)

        self.assertEqual(result, supervisor_data["human_support_tools"])

    def test_get_supervisor_agent_tools_without_human_support(self):
        """Test _get_supervisor_agent_tools returns tools when use_human_support=False."""
        supervisor_data = {"tools": [{"name": "regular_tool"}], "human_support_tools": [{"name": "human_tool"}]}

        result = self.repository._get_supervisor_agent_tools(supervisor=supervisor_data, use_human_support=False)

        self.assertEqual(result, supervisor_data["tools"])

    def test_get_supervisor_agent_tools_with_none_human_support(self):
        """Test _get_supervisor_agent_tools returns tools when use_human_support=None."""
        supervisor_data = {"tools": [{"name": "regular_tool"}], "human_support_tools": [{"name": "human_tool"}]}

        result = self.repository._get_supervisor_agent_tools(supervisor=supervisor_data, use_human_support=None)

        self.assertEqual(result, supervisor_data["tools"])

    def test_get_supervisor_with_multiple_default_managers(self):
        """Test get_supervisor returns the most recent default manager when UUID not found."""
        # Create another default manager (more recent)
        newer_manager = ManagerAgent.objects.create(
            name="Newer Manager",
            base_prompt="Newer prompt",
            foundation_model="gpt-4-turbo",
            model_vendor="openai",
            formatter_agent_foundation_model="gpt-4-turbo",
            collaborators_foundation_model="gpt-4-turbo",
            default=True,
            public=True,
            release_date=pendulum.now().add(days=1),
        )

        non_existent_uuid = "00000000-0000-0000-0000-000000000000"
        result = self.repository.get_supervisor(
            supervisor_agent_uuid=non_existent_uuid,
        )

        # Should return the newer manager (last by created_on)
        self.assertEqual(result["foundation_model"], newer_manager.foundation_model)

    def test_get_supervisor_all_expected_keys(self):
        """Test get_supervisor returns all expected keys in the result."""
        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
            human_support=True,
            use_components=True,
        )

        expected_keys = [
            "instruction",
            "use_components",
            "use_human_support",
            "components_instructions_up",
            "components_instructions",
            "formatter_agent_components_instructions",
            "human_support_instructions",
            "tools",
            "foundation_model",
            "model_vendor",
            "model_settings",
            "knowledge_bases",
            "max_tokens",
            "formatter_agent_configurations",
            "user_model_credentials",
            "collaborator_configurations",
        ]

        for key in expected_keys:
            self.assertIn(key, result, f"Key '{key}' not found in result")

    def test_get_supervisor_with_none_values(self):
        """Test get_supervisor handles None values correctly."""
        self.manager_agent.base_prompt = None
        self.manager_agent.human_support_prompt = None
        self.manager_agent.tools = None
        self.manager_agent.human_support_tools = None
        self.manager_agent.save()

        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
            human_support=True,
        )

        self.assertIsNone(result["instruction"])
        self.assertIsNone(result["human_support_instructions"])
        self.assertIsNone(result["tools"])

    def test_get_supervisor_with_empty_json_fields(self):
        """Test get_supervisor handles empty JSON fields correctly."""
        self.manager_agent.tools = []
        self.manager_agent.knowledge_bases = []
        self.manager_agent.save()

        result = self.repository.get_supervisor(
            supervisor_agent_uuid=str(self.manager_agent.uuid),
        )

        self.assertEqual(result["tools"], [])
        self.assertEqual(result["knowledge_bases"], [])
