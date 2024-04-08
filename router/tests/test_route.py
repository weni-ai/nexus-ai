
from __future__ import absolute_import, unicode_literals
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")

django.setup()


import uuid

from nexus.users.models import User
from nexus.orgs.models import Org
from nexus.actions.models import Flow
from nexus.intelligences.models import (
    IntegratedIntelligence, ContentBase, ContentBaseAgent
)


from router.tests.test_main import clean_db
from router.classifiers import Classifier
# from router.main import dispatch, route
from router.route import route
from router.entities import (
    FlowDTO, Message
)


from router.tests.mocks import *


# def create_objects():
#     user  = User.objects.create(email='test@user.com')

#     org = Org.objects.create(created_by=user, name='Test Org')
#     project = org.projects.create(uuid="7886d8d1-7bdc-4e85-a7fc-220e2256c11b", name="Test Project", created_by=user)

#     intelligence = org.intelligences.create(name="Test Intel", created_by=user)

#     integrated_intel = IntegratedIntelligence.objects.create(
#         project=project,
#         intelligence=intelligence,
#         created_by=user,
#     )

#     content_base = ContentBase.objects.create(
#         title='test content base', intelligence=intelligence, created_by=user, is_router=True
#     )

#     agent = ContentBaseAgent.objects.create(
#         name="Doris",
#         role="Vendas",
#         personality="Criativa",
#         goal="",
#         content_base=content_base
#     )
#     flow = Flow.objects.create(
#         content_base=content_base,
#         uuid=uuid.uuid4(),
#         name="Compras",
#         prompt="Fluxo de compras de roupas"
#     )
#     fallback = Flow.objects.create(
#         content_base=content_base,
#         uuid=uuid.uuid4(),
#         name="Fluxo de fallback",
#         prompt="Fluxo de fallback",
#         fallback=True,
#     )

#     return [user, org, project, intelligence, integrated_intel, content_base, agent, flow, fallback]


# def mock_messages(classification: str):
#     clean_db()
#     objects = create_objects()

#     content_base = objects[5]
#     agent = objects[6]
#     flow = objects[7]
#     fallback_flow = objects[8]

#     project_uuid = str(uuid.uuid4())

#     message = Message(
#         project_uuid=project_uuid,
#         text="Lorem Ipsum",
#         contact_urn="telegram:844380532"
#     )

#     content_base_repository = ContentBaseTestRepository(content_base, agent)
#     flows_repository = FlowsTestRepository(fallback_flow)

#     flows = [
#         FlowDTO(
#             uuid=str(flow.uuid),
#             name=flow.name,
#             prompt=flow.prompt,
#             fallback=flow.fallback,
#             content_base_uuid=str(flow.content_base.uuid),
#         )
#     ]

#     llm_type = "chatgpt"
#     llm_client = MockLLMClient.get_by_type(llm_type)

#     route(
#         classification=classification,
#         message=message,
#         content_base_repository=content_base_repository,
#         flows_repository=flows_repository,
#         flows=flows,
#         indexer=MockIndexer(),
#         llm_client=llm_client(),
#         direct_message=MockBroadcastHTTPClient(),
#         flow_start=MockFlowStartHTTPClient()
#     )




import unittest

class TestRoute(unittest.TestCase):

    def tearDown(self) -> None:
        clean_db()

    def setUp(self):
        clean_db()
        self.user  = User.objects.create(email='test@user.com')

        self.org = Org.objects.create(created_by=self.user, name='Test Org')
        self.project = self.org.projects.create(uuid="7886d8d1-7bdc-4e85-a7fc-220e2256c11b", name="Test Project", created_by=self.user)
        self.intelligence = self.org.intelligences.create(name="Test Intel", created_by=self.user)
        self.content_base = ContentBase.objects.create(
            title='test content base', intelligence=self.intelligence, created_by=self.user, is_router=True
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
            goal="",
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
    
    def test_route_other(self):
        print("\n[Test: Other]")
        self.mock_messages(
            Classifier.CLASSIFICATION_OTHER,
            fallback_flow=self.fallback
        )

    def test_route_other_no_fallback(self):
        print("\n[Test: Other no fallback]")
        self.fallback.delete()
        self.mock_messages(Classifier.CLASSIFICATION_OTHER)

    def test_route_classify(self):
        print("\n[Test: Classify]")
        self.mock_messages(self.flow.name)



    def mock_messages(
            self,
            classification: str,
            fallback_flow = None

        ):
        content_base = self.content_base
        agent = self.agent
        flow = self.flow

        project_uuid = str(self.project.uuid)

        message = Message(
            project_uuid=project_uuid,
            text="Lorem Ipsum",
            contact_urn="telegram:844380532"
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

        route(
            classification=classification,
            message=message,
            content_base_repository=content_base_repository,
            flows_repository=flows_repository,
            flows=flows,
            indexer=MockIndexer(),
            llm_client=llm_client(),
            direct_message=MockBroadcastHTTPClient(),
            flow_start=MockFlowStartHTTPClient()
        )