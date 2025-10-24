
from django.test import TestCase

from inline_agents.backends.openai.backend import OpenAISupervisorRepository
from inline_agents.backends.openai.tests.openai_factory import OpenAISupervisorFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class OpenAISupervisorRepositoryTestCase(TestCase):
    def setUp(self):
        """Set up test data before each test method."""
        self.project = ProjectFactory()
        self.supervisor = OpenAISupervisorFactory()

    def test_get_supervisor_success(self):
        """Test successful retrieval of supervisor with all attributes."""
        result = OpenAISupervisorRepository.get_supervisor(self.project)

        expected_keys = [
            "instruction", "use_components", "use_human_support", "components_instructions",
            "formatter_agent_components_instructions", "components_instructions_up", "human_support_instructions",
            "tools", "foundation_model", "knowledge_bases", "prompt_override_configuration", 
            "default_instructions_for_collaborators", "max_tokens"
        ]
        self.assertEqual(set(result.keys()), set(expected_keys))
        self.assertEqual(result["foundation_model"], self.supervisor.foundation_model)
        self.assertEqual(result["knowledge_bases"], self.supervisor.knowledge_bases)
        self.assertEqual(result["prompt_override_configuration"], self.supervisor.prompt_override_configuration)

    def test_get_supervisor_instructions_default_case(self):
        """Test _get_supervisor_instructions when project has no special flags."""
        self.project.use_components = False
        self.project.human_support = False
        self.project.save()

        result = OpenAISupervisorRepository._get_supervisor_instructions(self.project, self.supervisor)
        self.assertEqual(result, self.supervisor.instruction)

    def test_get_supervisor_instructions_components_only(self):
        """Test _get_supervisor_instructions when project uses components only."""
        self.project.use_components = True
        self.project.human_support = False
        self.project.save()

        # Create supervisor with specific values
        supervisor = OpenAISupervisorFactory(
            components_prompt="Components prompt"
        )

        result = OpenAISupervisorRepository._get_supervisor_instructions(self.project, supervisor)
        self.assertEqual(result, "Components prompt")

    def test_get_supervisor_instructions_human_support_only(self):
        """Test _get_supervisor_instructions when project has human support only."""
        self.project.use_components = False
        self.project.human_support = True
        self.project.save()

        # Create supervisor with specific values
        supervisor = OpenAISupervisorFactory(
            human_support_prompt="Human support prompt"
        )

        result = OpenAISupervisorRepository._get_supervisor_instructions(self.project, supervisor)
        self.assertEqual(result, "Human support prompt")

    def test_get_supervisor_instructions_components_and_human_support(self):
        """Test _get_supervisor_instructions when project has both components and human support."""
        self.project.use_components = True
        self.project.human_support = True
        self.project.save()

        # Create supervisor with specific values
        supervisor = OpenAISupervisorFactory(
            components_human_support_prompt="Components + Human support prompt"
        )

        result = OpenAISupervisorRepository._get_supervisor_instructions(self.project, supervisor)
        self.assertEqual(result, "Components + Human support prompt")

    def test_get_supervisor_tools_default_case(self):
        """Test _get_supervisor_tools when project has no human support."""
        self.project.human_support = False
        self.project.save()

        result = OpenAISupervisorRepository._get_supervisor_tools(self.project, self.supervisor)
        self.assertEqual(result, self.supervisor.action_groups)

    def test_get_supervisor_tools_human_support(self):
        """Test _get_supervisor_tools when project has human support."""
        self.project.human_support = True
        self.project.save()

        result = OpenAISupervisorRepository._get_supervisor_tools(self.project, self.supervisor)
        self.assertEqual(result, self.supervisor.human_support_action_groups)

    def test_get_supervisor_instructions_with_none_values(self):
        """Test _get_supervisor_instructions when some prompt fields are None."""
        supervisor = OpenAISupervisorFactory(
            components_prompt=None,
            human_support_prompt=None,
            components_human_support_prompt=None
        )

        self.project.use_components = True
        self.project.human_support = False
        self.project.save()

        result = OpenAISupervisorRepository._get_supervisor_instructions(self.project, supervisor)
        self.assertIsNone(result)  # Should be None

        # Test human support only with None value
        self.project.use_components = False
        self.project.human_support = True
        self.project.save()

        result = OpenAISupervisorRepository._get_supervisor_instructions(self.project, supervisor)
        self.assertIsNone(result)  # Should be None

        # Test both with None value
        self.project.use_components = True
        self.project.human_support = True
        self.project.save()

        result = OpenAISupervisorRepository._get_supervisor_instructions(self.project, supervisor)
        self.assertIsNone(result)  # Should be None

    def test_get_supervisor_tools_with_none_values(self):
        """Test _get_supervisor_tools when human_support_action_groups is None."""
        supervisor = OpenAISupervisorFactory(
            human_support_action_groups=None
        )

        self.project.human_support = True
        self.project.save()

        result = OpenAISupervisorRepository._get_supervisor_tools(self.project, supervisor)
        self.assertIsNone(result)

    def test_get_supervisor_multiple_supervisors(self):
        """Test that get_supervisor returns the last supervisor by ID."""
        supervisor1 = OpenAISupervisorFactory()
        supervisor2 = OpenAISupervisorFactory()
        supervisor3 = OpenAISupervisorFactory()

        result = OpenAISupervisorRepository.get_supervisor(self.project)

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
            max_tokens=4096
        )

        result = OpenAISupervisorRepository.get_supervisor(self.project)

        self.assertEqual(result["instruction"], "Components + Human support prompt")
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

        supervisor_none = OpenAISupervisorFactory(
            default_instructions_for_collaborators=None
        )
        self.assertIsNone(supervisor_none.default_instructions_for_collaborators)

        supervisor_empty = OpenAISupervisorFactory(
            default_instructions_for_collaborators=""
        )
        self.assertEqual(supervisor_empty.default_instructions_for_collaborators, "")

    def test_get_supervisor_includes_default_instructions_for_collaborators(self):
        """Test that get_supervisor includes default_instructions_for_collaborators in the result."""
        OpenAISupervisorFactory(
            default_instructions_for_collaborators="Be concise and professional in all responses."
        )

        result = OpenAISupervisorRepository.get_supervisor(self.project)

        self.assertIn("default_instructions_for_collaborators", result)
        self.assertEqual(result["default_instructions_for_collaborators"], "Be concise and professional in all responses.")
