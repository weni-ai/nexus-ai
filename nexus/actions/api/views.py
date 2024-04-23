import os
from typing import Dict, List

from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from nexus.actions.models import Flow

from nexus.actions.api.serializers import FlowSerializer

from nexus.usecases import orgs
from nexus.usecases.actions.list import ListFlowsUseCase
from nexus.usecases.actions.create import CreateFlowDTO, CreateFlowsUseCase
from nexus.usecases.actions.delete import DeleteFlowsUseCase, DeleteFlowDTO
from nexus.usecases.actions.update import UpdateFlowsUseCase, UpdateFlowDTO
from nexus.usecases.actions.retrieve import RetrieveFlowsUseCase, FlowDoesNotExist
from nexus.usecases.intelligences.exceptions import IntelligencePermissionDenied
from nexus.usecases.intelligences.get_by_uuid import get_llm_by_project_uuid

from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase

from nexus.intelligences.llms.client import LLMClient

from nexus.orgs import permissions

from router.repositories.orm import FlowsORMRepository, ContentBaseORMRepository
from router.classifiers.zeroshot import ZeroshotClassifier
from router.classifiers import classify
from router.entities import (
    AgentDTO,
    ContentBaseDTO,
    FlowDTO,
    LLMSetupDTO,
    Message,
)

from router.clients.preview.simulator.broadcast import SimulateBroadcast
from router.clients.preview.simulator.flow_start import SimulateFlowStart

from router.route import route


class SearchFlowView(APIView):
    def format_response(self, data: Dict) -> Dict:

        if data.get('next'):
            next_page = data.get('next').split("?")
            next_page = f'?{next_page[1]}'
            data.update({'next': next_page})
        if data.get('previous'):
            prev_page = data.get('previous').split("?")
            prev_page = f'?{prev_page[1]}'
            data.update({'previous': prev_page})

        return data

    def get(self, request, *args, **kwargs):

        project_uuid = kwargs.get('project_uuid')
        name = request.query_params.get("name")
        page_size = request.query_params.get('page_size')
        page = request.query_params.get('page')

        data: Dict = ListFlowsUseCase().search_flows_by_project(project_uuid, name, page_size, page)

        return Response(self.format_response(data))


class FlowsViewset(
    ModelViewSet,
):
    serializer_class = FlowSerializer
    lookup_url_kwarg = 'flow_uuid'

    def _permission_mapper(self):
        return {
            "create": permissions.can_create_content_bases,
            "read": permissions.can_list_content_bases,
            "update": permissions.can_edit_content_bases,
            "delete": permissions.can_delete_content_bases,
        }

    def get_queryset(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            return Flow.objects.none()  # pragma: no cover
        super().get_serializer(*args, **kwargs)

    def check_user_permissions(self, request, project_uuid: str, method: str):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        org = org_use_case.get_org_by_project_uuid(project_uuid)

        has_permission = self._permission_mapper().get(method)(request.user, org)

        if not has_permission:
            raise IntelligencePermissionDenied()

    def create(self, request, *args, **kwargs):
        try:
            project_uuid = kwargs.get('project_uuid')

            self.check_user_permissions(request, project_uuid, "create")

            create_dto = CreateFlowDTO(
                project_uuid=project_uuid,
                flow_uuid=request.data.get("uuid"),
                name=request.data.get("name"),
                prompt=request.data.get("prompt"),
                fallback=request.data.get("fallback"),
            )

            flows = CreateFlowsUseCase().create_flow(create_dto)
            data = FlowSerializer(flows).data
            return Response(data=data, status=status.HTTP_201_CREATED)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def retrieve(self, request, *args, **kwargs):
        try:
            flow_uuid = kwargs.get('flow_uuid')
            project_uuid = kwargs.get('project_uuid')

            self.check_user_permissions(request, project_uuid, "read")

            flow = RetrieveFlowsUseCase().retrieve_flow_by_uuid(flow_uuid=flow_uuid)
            data = FlowSerializer(flow).data
            return Response(data=data, status=status.HTTP_200_OK)

        except FlowDoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def list(self, request, *args, **kwargs):
        try:
            project_uuid = kwargs.get('project_uuid')

            self.check_user_permissions(request, project_uuid, "read")

            flows = ListFlowsUseCase().list_flows_by_project_uuid(project_uuid)
            data = FlowSerializer(flows, many=True).data
            return Response(data=data, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def update(self, request, *args, **kwargs):
        flow_dto = UpdateFlowDTO(
            flow_uuid=kwargs.get("flow_uuid"),
            prompt=request.data.get("prompt")
        )
        project_uuid = kwargs.get('project_uuid')
        self.check_user_permissions(request, project_uuid, "update")
        flow = UpdateFlowsUseCase().update_flow(flow_dto)
        data = FlowSerializer(flow).data
        return Response(data=data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        try:
            project_uuid = kwargs.get('project_uuid')
            flow_dto = DeleteFlowDTO(
                flow_uuid=kwargs.get("flow_uuid"),
            )
            self.check_user_permissions(request, project_uuid, "update")
            DeleteFlowsUseCase().hard_delete_flow(flow_dto)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except FlowDoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


class MessagePreviewView(APIView):
    def _permission_mapper(self):
        return {
            "create": permissions.can_create_content_bases,
            "read": permissions.can_list_content_bases,
            "update": permissions.can_edit_content_bases,
            "delete": permissions.can_delete_content_bases,
        }

    def check_user_permissions(self, request, project_uuid: str, method: str):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        org = org_use_case.get_org_by_project_uuid(project_uuid)

        has_permission = self._permission_mapper().get(method)(request.user, org)

        if not has_permission:
            raise IntelligencePermissionDenied()

    def post(self, request, *args, **kwargs):
        try:

            data = request.data
            project_uuid = kwargs.get("project_uuid")

            self.check_user_permissions(request, project_uuid, "read")

            flows_repository = FlowsORMRepository()
            content_base_repository = ContentBaseORMRepository()

            message = Message(
                project_uuid=project_uuid,
                text=data.get("text"),
                contact_urn=data.get("contact_urn"),
            )

            project_uuid: str = message.project_uuid

            flows: List[FlowDTO] = flows_repository.project_flows(project_uuid, False)

            content_base: ContentBaseDTO = content_base_repository.get_content_base_by_project(message.project_uuid)

            agent: AgentDTO = content_base_repository.get_agent(content_base.uuid)
            agent = agent.set_default_if_null()

            classification: str = classify(ZeroshotClassifier(chatbot_goal=agent.goal), message.text, flows)

            print(f"[+ Mensagem classificada: {classification} +]")

            llm_model = get_llm_by_project_uuid(project_uuid)

            llm_config = LLMSetupDTO(
                model=llm_model.model.lower(),
                model_version=llm_model.setup.get("version"),
                temperature=llm_model.setup.get("temperature"),
                top_k=llm_model.setup.get("top_k"),
                top_p=llm_model.setup.get("top_p"),
                token=llm_model.setup.get("token"),
                max_length=llm_model.setup.get("max_length"),
                max_tokens=llm_model.setup.get("max_tokens"),
            )

            print(f"[+ LLM escolhido {llm_config.model} +]")

            llm_client = LLMClient.get_by_type(llm_config.model)
            llm_client: LLMClient = list(llm_client)[0](model_version=llm_config.model_version)

            if llm_config.model.lower() != "wenigpt":
                llm_client.api_key = llm_config.token

            print(f"[+ Modelo escolhido: {llm_config.model} :{llm_config.model_version} +]")

            broadcast = SimulateBroadcast(os.environ.get('FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_INTERNAL_TOKEN'))
            flow_start = SimulateFlowStart(os.environ.get('FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_INTERNAL_TOKEN'))
            flows_user_email = os.environ.get("FLOW_USER_EMAIL")

            response: dict = route(
                classification=classification,
                message=message,
                content_base_repository=content_base_repository,
                flows_repository=flows_repository,
                indexer=SentenXFileDataBase(),
                llm_client=llm_client,
                direct_message=broadcast,
                flow_start=flow_start,
                llm_config=llm_config,
                flows_user_email=flows_user_email
            )
            return Response(data=response)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
