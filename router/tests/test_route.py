
from __future__ import absolute_import, unicode_literals
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")

django.setup()


import uuid

from django.conf import settings
from django.test import TestCase

from nexus.users.models import User
from nexus.orgs.models import Org
from nexus.actions.models import Flow
from nexus.intelligences.models import (
    IntegratedIntelligence, ContentBase, ContentBaseAgent, ContentBaseInstruction
)
from nexus.usecases.intelligences.get_by_uuid import get_llm_by_project_uuid
from nexus.usecases.intelligences.intelligences_dto import LLMDTO
from nexus.usecases.intelligences.create import create_llm


from router.classifiers import Classifier
from router.route import route
from router.entities import (
    FlowDTO, Message
)
from router.tests.mocks import *
from nexus.intelligences.llms.chatgpt import ChatGPTClient
from nexus.intelligences.llms.wenigpt import WeniGPTClient

from router.clients.preview.simulator.broadcast import SimulateBroadcast
from router.clients.preview.simulator.flow_start import SimulateFlowStart

class RouteTestCase(TestCase):
    def setUp(self) -> None:
        self.user  = User.objects.create(email='test@user.com')

        project_name = "Test Project"

        self.org = Org.objects.create(created_by=self.user, name='Test Org')
        self.org.authorizations.create(role=3, user=self.user)
        self.project = self.org.projects.create(uuid="7886d8d1-7bdc-4e85-a7fc-220e2256c11b", name=project_name, created_by=self.user)
        self.intelligence = self.org.intelligences.create(name=project_name, created_by=self.user)
        self.content_base = ContentBase.objects.create(
            title=project_name, intelligence=self.intelligence, created_by=self.user, is_router=True
        )
        self.integrated_intel = IntegratedIntelligence.objects.create(
            project=self.project,
            intelligence=self.intelligence,
            created_by=self.user,
        )

        self.agent = ContentBaseAgent.objects.create(
            name="Doris",
            role="Vendas",
            personality="Criativa",
            goal="Vender os produtos",
            content_base=self.content_base
        )
        self.flow = Flow.objects.create(
            content_base=self.content_base,
            uuid=uuid.uuid4(),
            name="Compras",
            prompt="Fluxo de compras de roupas"
        )
        self.fallback = Flow.objects.create(
            content_base=self.content_base,
            uuid=uuid.uuid4(),
            name="Fluxo de fallback",
            prompt="Fluxo de fallback",
            fallback=True,
        )
        self.instruction = ContentBaseInstruction.objects.create(content_base=self.content_base, instruction="Teste Instruction")

        llm_dto = LLMDTO(
            user_email=self.user.email,
            project_uuid=str(self.project.uuid),
            setup={
                'temperature': settings.WENIGPT_TEMPERATURE,
                'top_p': settings.WENIGPT_TOP_P,
                'top_k': settings.WENIGPT_TOP_K,
                'max_length': settings.WENIGPT_MAX_LENGHT,
            }
        )
        self.llm = create_llm(llm_dto=llm_dto)

    def test_chatgpt_prompt(self):
        from router.repositories.orm import ContentBaseORMRepository

        content_base = self.content_base

        content_base_repository = ContentBaseORMRepository()
        instructions: List[InstructionDTO] = content_base_repository.list_instructions(content_base.uuid)
        instructions: List[str] = [instruction.instruction for instruction in instructions]
        agent = self.agent

        chunks = ["Lorem Ipsum", "Dolor Sit Amet"]

        prompt = ChatGPTClient().format_prompt(instructions, chunks, agent.__dict__)
        # print(prompt)
        assert "{{" not in prompt
    
    def test_wenigpt_prompt(self):
        from router.repositories.orm import ContentBaseORMRepository

        content_base = self.content_base

        content_base_repository = ContentBaseORMRepository()
        instructions: List[InstructionDTO] = content_base_repository.list_instructions(content_base.uuid)
        instructions: List[str] = [instruction.instruction for instruction in instructions]
        agent = self.agent

        chunks = ["Lorem Ipsum", "Dolor Sit Amet"]
        question = "Ipsum Lorem"

        prompt = WeniGPTClient(model_version=settings.WENIGPT_FINE_TUNNING_DEFAULT_VERSION).format_prompt(instructions, chunks, agent.__dict__, question)
        assert "{{" not in prompt
    
    def test_wenigpt_no_context_prompt(self):
        from router.repositories.orm import ContentBaseORMRepository

        content_base = self.content_base

        content_base_repository = ContentBaseORMRepository()
        instructions: List[InstructionDTO] = content_base_repository.list_instructions(content_base.uuid)
        instructions: List[str] = [instruction.instruction for instruction in instructions]
        agent = self.agent

        chunks = []
        question = "Ipsum Lorem"

        prompt = WeniGPTClient(model_version=settings.WENIGPT_FINE_TUNNING_DEFAULT_VERSION).format_prompt(instructions, chunks, agent.__dict__, question)
        print(prompt)
        assert "{{" not in prompt
    
    def test_chatgpt_no_context_prompt(self):
        from router.repositories.orm import ContentBaseORMRepository

        content_base = self.content_base

        content_base_repository = ContentBaseORMRepository()
        instructions: List[InstructionDTO] = content_base_repository.list_instructions(content_base.uuid)
        agent = self.agent

        chunks = []

        prompt = ChatGPTClient().format_prompt(instructions, chunks, agent.__dict__)
        print(prompt)
        assert "{{" not in prompt

    def mock_messages(
            self,
            classification: str,
            fallback_flow = None,
            direct_message = MockBroadcastHTTPClient(),
            flow_start = MockFlowStartHTTPClient(),

        ):
        content_base = self.content_base
        agent = self.agent
        flow = self.flow

        project_uuid = str(self.project.uuid)

        message = Message(
            project_uuid=project_uuid,
            text="Lorem Ipsum",
            contact_urn="telegram:123455667"
        )

        content_base_repository = ContentBaseTestRepository(content_base, agent)
        flows_repository = FlowsTestRepository(flow, fallback_flow)

        flows = [
            FlowDTO(
                uuid=str(flow.uuid),
                name=flow.name,
                prompt=flow.prompt,
                fallback=flow.fallback,
                content_base_uuid=str(flow.content_base.uuid),
            )
        ]

        llm_type = "chatgpt"
        llm_client = MockLLMClient.get_by_type(llm_type)

        llm_config = get_llm_by_project_uuid(project_uuid)

        if llm_config.model.lower() != "wenigpt":
            llm_client.token = llm_config.setup.get("token")

        flow_user_email = "email@test.com"

        return route(
            classification=classification,
            message=message,
            content_base_repository=content_base_repository,
            flows_repository=flows_repository,
            indexer=MockIndexer(),
            llm_client=llm_client(),
            direct_message=direct_message,
            flow_start=flow_start,
            llm_config=llm_config,
            flows_user_email=flow_user_email,
        )
    
    def test_route_other(self):
        try:
            print("\n[Test: Other]")
            self.mock_messages(
                Classifier.CLASSIFICATION_OTHER,
                fallback_flow=self.fallback
            )
        except Exception as e:
            self.fail(f" test_route_other raised {e}!")

    def test_route_other_no_fallback(self):
        try:
            print("\n[Test: Other no fallback]")
            self.fallback.delete()
            self.mock_messages(Classifier.CLASSIFICATION_OTHER)
        except Exception as e:
            self.fail(f" test_route_other raised {e}!")

    def test_route_classify(self):
        try:
            print("\n[Test: Classify]")
            self.mock_messages(self.flow.name)
        except Exception as e:
            self.fail(f" test_route_other raised {e}!")

    def test_route_preview_other_with_fallback_flow(self):
        response = self.mock_messages(
            Classifier.CLASSIFICATION_OTHER,
            fallback_flow=self.fallback,
            direct_message=SimulateBroadcast(host=None, access_token=None),
            flow_start=SimulateFlowStart(host=None, access_token=None)
        )
        self.assertEquals(response.get("type"), "flowstart")

    def test_route_preview_other_no_fallback_flow(self):
        response = self.mock_messages(
            Classifier.CLASSIFICATION_OTHER,
            direct_message=SimulateBroadcast(host=None, access_token=None),
            flow_start=SimulateFlowStart(host=None, access_token=None)
        )
        self.assertEquals(response.get("type"), "broadcast")

    def test_route_preview_classify(self):
        response = self.mock_messages(
            self.flow.name,
            fallback_flow=self.fallback,
            direct_message=SimulateBroadcast(host=None, access_token=None),
            flow_start=SimulateFlowStart(host=None, access_token=None)
        )
        self.assertEquals(response.get("type"), "flowstart")

