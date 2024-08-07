from django.test import TestCase

from nexus.usecases.actions.tests.flow_factory import FlowFactory
from nexus.usecases.actions.update import UpdateFlowDTO, UpdateFlowsUseCase

from nexus.event_domain.recent_activity.mocks import mock_event_manager_notify


class TestUpdateFlowUseCase(TestCase):

    def setUp(self):
        self.flow_factory = FlowFactory()

    def test_update(self):
        update_dto = UpdateFlowDTO(
            flow_uuid=self.flow_factory.uuid,
            prompt="new prompt",
            name="new flow name"
        )

        update_usecase = UpdateFlowsUseCase(
            event_manager_notify=mock_event_manager_notify
        )

        updated_flow = update_usecase.update_flow(
            user=self.flow_factory.content_base.created_by,
            flow_dto=update_dto
        )

        self.assertEqual(updated_flow.prompt, update_dto.prompt)

    def test_update_name(self):
        update_dto = UpdateFlowDTO(
            flow_uuid=self.flow_factory.uuid,
            name="test flow name 2"
        )

        update_usecase = UpdateFlowsUseCase(
            event_manager_notify=mock_event_manager_notify
        )

        updated_flow = update_usecase.update_flow(
            user=self.flow_factory.content_base.created_by,
            flow_dto=update_dto
        )

        self.assertEqual(updated_flow.name, update_dto.name)
        self.assertEqual(updated_flow.prompt, self.flow_factory.prompt)
