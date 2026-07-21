from django.test import SimpleTestCase, override_settings

from inline_agents.backends.openai.components_debug import resolve_components_prompt_and_tools


class TestResolveComponentsPromptAndTools(SimpleTestCase):
    def test_disabled_when_use_components_false(self):
        with override_settings(
            COMPONENTS_DEBUG_INCLUDE_PROMPTS=True,
            COMPONENTS_DEBUG_INCLUDE_TOOLS=True,
        ):
            self.assertEqual(resolve_components_prompt_and_tools(False), (False, False))

    def test_defaults_enable_both_when_use_components_true(self):
        with override_settings(
            COMPONENTS_DEBUG_INCLUDE_PROMPTS=True,
            COMPONENTS_DEBUG_INCLUDE_TOOLS=True,
        ):
            self.assertEqual(resolve_components_prompt_and_tools(True), (True, True))

    def test_can_disable_prompts_only(self):
        with override_settings(
            COMPONENTS_DEBUG_INCLUDE_PROMPTS=False,
            COMPONENTS_DEBUG_INCLUDE_TOOLS=True,
        ):
            self.assertEqual(resolve_components_prompt_and_tools(True), (False, True))

    def test_can_disable_tools_only(self):
        with override_settings(
            COMPONENTS_DEBUG_INCLUDE_PROMPTS=True,
            COMPONENTS_DEBUG_INCLUDE_TOOLS=False,
        ):
            self.assertEqual(resolve_components_prompt_and_tools(True), (True, False))
