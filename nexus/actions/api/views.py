from typing import Dict

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
from nexus.orgs import permissions

from nexus.internals.flows import FlowsRESTClient


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
