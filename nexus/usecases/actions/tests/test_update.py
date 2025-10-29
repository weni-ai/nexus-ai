from django.test import TestCase

from nexus.event_domain.recent_activity.mocks import mock_event_manager_notify
from nexus.usecases.actions.tests.flow_factory import FlowFactory, TemplateActionFactory
from nexus.usecases.actions.update import (
    UpdateActionFlowDTO,
    UpdateFlowsUseCase,
    UpdateTemplateActionDTO,
    UpdateTemplateActionUseCase,
)


class TestUpdateFlowUseCase(TestCase):
    def setUp(self):
        self.flow_factory = FlowFactory()

    def test_update(self):
        update_dto = UpdateActionFlowDTO(uuid=str(self.flow_factory.uuid), prompt="new prompt", name="new flow name")

        update_usecase = UpdateFlowsUseCase(event_manager_notify=mock_event_manager_notify)

        updated_flow = update_usecase.update_flow(user=self.flow_factory.content_base.created_by, flow_dto=update_dto)

        self.assertEqual(updated_flow.prompt, update_dto.prompt)

    def test_update_name(self):
        update_dto = UpdateActionFlowDTO(uuid=str(self.flow_factory.uuid), name="test flow name 2")

        update_usecase = UpdateFlowsUseCase(event_manager_notify=mock_event_manager_notify)

        updated_flow = update_usecase.update_flow(user=self.flow_factory.content_base.created_by, flow_dto=update_dto)

        self.assertEqual(updated_flow.name, update_dto.name)
        self.assertEqual(updated_flow.prompt, self.flow_factory.prompt)


class TestUpdateTemplateActionUseCase(TestCase):
    def setUp(self):
        self.template_action_factory = TemplateActionFactory()
        self.usecase = UpdateTemplateActionUseCase()

    def test_update(self):
        update_dto = UpdateTemplateActionDTO(
            template_action_uuid=self.template_action_factory.uuid, prompt="new prompt", name="new template action name"
        )

        updated_template_action = self.usecase.update_template_action(template_action_dto=update_dto)

        self.assertEqual(updated_template_action.prompt, update_dto.prompt)

    def test_update_name(self):
        update_dto = UpdateTemplateActionDTO(
            template_action_uuid=self.template_action_factory.uuid,
            name="test template action name 2",
        )

        updated_template_action = self.usecase.update_template_action(template_action_dto=update_dto)

        self.assertEqual(updated_template_action.name, update_dto.name)
        self.assertEqual(updated_template_action.prompt, self.template_action_factory.prompt)

    def test_update_prompt(self):
        update_dto = UpdateTemplateActionDTO(
            template_action_uuid=self.template_action_factory.uuid,
            prompt="test template action prompt 2",
        )

        updated_template_action = self.usecase.update_template_action(template_action_dto=update_dto)

        self.assertEqual(updated_template_action.prompt, update_dto.prompt)
        self.assertEqual(updated_template_action.name, self.template_action_factory.name)
