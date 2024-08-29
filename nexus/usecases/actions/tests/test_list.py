from django.test import TestCase

from nexus.usecases.actions.tests.flow_factory import TemplateActionFactory
from nexus.usecases.actions.list import ListTemplateActionUseCase


class TestListTemplateActionUseCase(TestCase):

    def setUp(self) -> None:
        self.template_action_factory = TemplateActionFactory()
        self.usecase = ListTemplateActionUseCase()

    def test_list(self):
        template_action = self.template_action_factory
        template_actions = self.usecase.list_template_action()

        self.assertEqual(len(template_actions), 1)
        self.assertEqual(template_actions[0].name, template_action.name)
        self.assertEqual(template_actions[0].prompt, template_action.prompt)
        self.assertEqual(template_actions[0].action_type, template_action.action_type)
        self.assertEqual(template_actions[0].group, template_action.group)
