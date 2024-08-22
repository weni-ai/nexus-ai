from uuid import uuid4

from nexus.usecases.actions.create import CreateFlowDTO, CreateFlowsUseCase
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory, IntegratedIntelligenceFactory


from django.test import TestCase


class CreateFlowsUseCaseTest(TestCase):

    def setUp(self):
        integrated_intelligence = IntegratedIntelligenceFactory()
        self.project = integrated_intelligence.project
        self.content_base = ContentBaseFactory(
            intelligence=integrated_intelligence.intelligence,
            is_router=True
        )

    def test_create_flow(self):
        flow_uuid = str(uuid4())
        create_dto = CreateFlowDTO(
            project_uuid=self.project.uuid,
            flow_uuid=flow_uuid,
            name="flow_name",
            action_type="custom",
            prompt="flow_prompt",
            fallback=False
        )

        use_case = CreateFlowsUseCase()
        flow = use_case.create_flow(create_dto)

        self.assertEqual(flow.name, "flow_name")
        self.assertEqual(flow.prompt, "flow_prompt")
        self.assertEqual(flow.fallback, False)
        self.assertEqual(flow.action_type, "custom")
        self.assertEqual(flow.content_base, self.content_base)
        self.assertEqual(flow.uuid, flow_uuid)

    def test_blank_prompt_for_custom_flow(self):
        flow_uuid = str(uuid4())
        create_dto = CreateFlowDTO(
            project_uuid=self.project.uuid,
            flow_uuid=flow_uuid,
            name="flow_name",
            action_type="custom",
            prompt=None,
            fallback=False
        )

        use_case = CreateFlowsUseCase()
        with self.assertRaises(ValueError):
            use_case.create_flow(create_dto)

    def test_blank_prompt_for_whatsapp_cart_flow(self):
        flow_uuid = str(uuid4())
        create_dto = CreateFlowDTO(
            project_uuid=self.project.uuid,
            flow_uuid=flow_uuid,
            name="flow_name",
            action_type="whatsapp_cart",
            prompt=None,
            fallback=False
        )

        use_case = CreateFlowsUseCase()
        flow = use_case.create_flow(create_dto)

        self.assertEqual(flow.name, "flow_name")
        self.assertEqual(flow.prompt, None)
        self.assertEqual(flow.fallback, False)
        self.assertEqual(flow.action_type, "whatsapp_cart")
        self.assertEqual(flow.content_base, self.content_base)
        self.assertEqual(flow.uuid, flow_uuid)
