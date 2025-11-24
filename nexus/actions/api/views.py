from typing import Dict

from celery.exceptions import TaskRevokedError
from django.core.exceptions import PermissionDenied
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from nexus.actions.api.serializers import (
    FlowSerializer,
    TemplateActionSerializer,
)
from nexus.actions.models import Flow, TemplateAction
from nexus.authentication import AUTHENTICATION_CLASSES
from nexus.orgs.permissions import is_super_user
from nexus.projects.api.permissions import ProjectPermission
from nexus.projects.exceptions import ProjectAuthorizationDenied
from nexus.projects.permissions import has_external_general_project_permission
from nexus.usecases import projects
from nexus.usecases.actions.create import (
    CreateFlowDTO,
    CreateFlowsUseCase,
    CreateTemplateActionUseCase,
    GenerateFlowNameUseCase,
)
from nexus.usecases.actions.delete import (
    DeleteFlowDTO,
    DeleteFlowsUseCase,
    delete_template_action,
)
from nexus.usecases.actions.list import (
    ListFlowsUseCase,
    ListTemplateActionUseCase,
)
from nexus.usecases.actions.retrieve import (
    FlowDoesNotExist,
    RetrieveFlowsUseCase,
)
from nexus.usecases.actions.update import (
    UpdateActionFlowDTO,
    UpdateFlowsUseCase,
    UpdateTemplateActionDTO,
    UpdateTemplateActionUseCase,
)
from nexus.usecases.intelligences.exceptions import (
    IntelligencePermissionDenied,
)
from router.entities import Message as UserMessage
from router.tasks.invoke import start_inline_agents
from router.tasks.tasks import start_route


class SearchFlowView(APIView):
    def format_response(self, data: Dict) -> Dict:
        if data.get("next"):
            next_page = data.get("next").split("?")
            next_page = f"?{next_page[1]}"
            data.update({"next": next_page})
        if data.get("previous"):
            prev_page = data.get("previous").split("?")
            prev_page = f"?{prev_page[1]}"
            data.update({"previous": prev_page})

        return data

    def get(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        name = request.query_params.get("name")
        page_size = request.query_params.get("page_size")
        page = request.query_params.get("page")

        data: Dict = ListFlowsUseCase().search_flows_by_project(project_uuid, name, page_size, page)

        return Response(self.format_response(data))


class FlowsViewset(
    ModelViewSet,
):
    serializer_class = FlowSerializer
    permission_classes = [ProjectPermission]
    lookup_url_kwarg = "flow_uuid"

    def get_queryset(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            return Flow.objects.none()  # pragma: no cover
        super().get_serializer(*args, **kwargs)

    def create(self, request, *args, **kwargs):
        try:
            project_uuid = kwargs.get("project_uuid")
            project = projects.get_project_by_uuid(project_uuid)
            user = request.user

            flow_uuid = request.data.get("uuid")
            fallback = request.data.get("fallback")

            action_template_uuid = request.data.get("action_template_uuid", None)

            name = request.data.get("name")
            prompt = request.data.get("prompt", "")
            action_type = request.data.get("action_type", "custom")
            group = request.data.get("group", "custom")
            send_to_llm = request.data.get("send_to_llm", False)

            if action_template_uuid:
                template = TemplateAction.objects.get(uuid=action_template_uuid)
                name = template.name
                prompt = template.prompt if template.prompt else ""
                action_type = template.action_type
                group = template.group

            create_dto = CreateFlowDTO(
                project_uuid=project_uuid,
                flow_uuid=flow_uuid,
                name=name,
                prompt=prompt,
                fallback=fallback,
                send_to_llm=send_to_llm,
                action_type=action_type,
                template=template if action_template_uuid else None,
                group=group,
            )

            usecase = CreateFlowsUseCase()
            flows = usecase.create_flow(
                user=user,
                project=project,
                create_dto=create_dto,
            )
            data = FlowSerializer(flows).data
            return Response(data=data, status=status.HTTP_201_CREATED)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def retrieve(self, request, *args, **kwargs):
        try:
            flow_uuid = kwargs.get("flow_uuid")

            flow = RetrieveFlowsUseCase().retrieve_flow_by_uuid(uuid=flow_uuid)
            data = FlowSerializer(flow).data
            return Response(data=data, status=status.HTTP_200_OK)

        except FlowDoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def list(self, request, *args, **kwargs):
        try:
            project_uuid = kwargs.get("project_uuid")

            flows = ListFlowsUseCase().list_flows_by_project_uuid(project_uuid)
            data = FlowSerializer(flows, many=True).data
            return Response(data=data, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def update(self, request, *args, **kwargs):
        flow_dto = UpdateActionFlowDTO(
            uuid=kwargs.get("flow_uuid"),  # TODO:  change lookup url
            flow_uuid=request.data.get("flow_uuid"),
            prompt=request.data.get("prompt"),
            name=request.data.get("name"),
            send_to_llm=request.data.get("send_to_llm", False),
        )
        user = request.user

        flow = UpdateFlowsUseCase().update_flow(flow_dto=flow_dto, user=user)
        data = FlowSerializer(flow).data
        return Response(data=data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        try:
            project_uuid = kwargs.get("project_uuid")
            flow_dto = DeleteFlowDTO(
                flow_uuid=kwargs.get("flow_uuid"),
            )
            project = projects.get_project_by_uuid(project_uuid)
            user = request.user

            DeleteFlowsUseCase().hard_delete_flow(flow_dto=flow_dto, user=user, project=project)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except FlowDoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


class MessagePreviewView(APIView):
    permission_classes = [ProjectPermission]

    def post(self, request, *args, **kwargs):
        try:
            project_uuid = kwargs.get("project_uuid")
            project = projects.get_project_by_uuid(project_uuid)

            data = request.data
            language = data.get("language", "en")
            message = UserMessage(
                project_uuid=project_uuid,
                text=data.get("text"),
                contact_urn=data.get("contact_urn"),
                attachments=data.get("attachments", []),
                metadata=data.get("metadata", {}),
            )
            if project.inline_agent_switch:
                import logging

                logging.getLogger(__name__).info("Starting Inline Agent")
                start_inline_agents.apply_async(
                    kwargs={
                        "message": message.dict(),
                        "preview": True,
                        "user_email": request.user.email,
                        "language": language,
                    },
                    queue="celery",
                )
                return Response(data={"type": "preview", "message": "Processing started", "fonts": []})
            else:
                task = start_route.delay(message=message.__dict__, preview=True)
                response = task.wait()

            return Response(data=response)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except TaskRevokedError:
            return Response(data={"type": "cancelled", "message": "", "fonts": []})


class GenerateActionNameView(APIView):
    permission_classes = [ProjectPermission]

    def post(self, request, *args, **kwargs):
        try:
            data = request.data
            chatbot_goal = data.get("chatbot_goal")
            context = data.get("context")

            usecase = GenerateFlowNameUseCase()
            response = usecase.generate_action_name(chatbot_goal, context)
            return Response(data=response)
        except ProjectAuthorizationDenied:
            return Response(status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"Error": str(e)})


class TemplateActionView(ModelViewSet):
    serializer_class = TemplateActionSerializer
    authentication_classes = AUTHENTICATION_CLASSES

    def get_queryset(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            return TemplateAction.objects.none()  # pragma: no cover
        super().get_serializer(*args, **kwargs)

    def list(self, request, *args, **kwargs):
        try:
            language = request.query_params.get("language", "pt-br")
            project_uuid = kwargs.get("project_uuid")

            authorization_header = request.headers.get("Authorization", "Bearer unauthorized")
            super_user = is_super_user(authorization_header)

            if not super_user:
                has_external_general_project_permission(method="get", request=request, project_uuid=project_uuid)

            template_actions = ListTemplateActionUseCase().list_template_action(language=language)
            serializer = self.get_serializer(template_actions, many=True)
            return Response(data=serializer.data)
        except ProjectAuthorizationDenied:
            return Response(status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"Error": str(e)})

    def create(self, request, *args, **kwargs):
        try:
            authorization_header = request.headers.get("Authorization", "Bearer unauthorized")
            if not is_super_user(authorization_header):
                raise PermissionDenied("You has not permission to do that.")

            data = request.data
            name = data.get("name")
            prompt = data.get("prompt")
            action_type = data.get("action_type")
            group = data.get("group")
            display_prompt = data.get("display_prompt", prompt)

            template_action = CreateTemplateActionUseCase().create_template_action(
                name=name, prompt=prompt, action_type=action_type, group=group, display_prompt=display_prompt
            )
            serializer = self.get_serializer(template_action)
            return Response(data=serializer.data)
        except PermissionDenied:
            return Response(status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"Error": str(e)})

    def destroy(self, request, *args, **kwargs):
        try:
            authorization_header = request.headers.get("Authorization", "Bearer unauthorized")
            if not is_super_user(authorization_header):
                raise PermissionDenied("You has not permission to do that.")

            template_action_uuid = kwargs.get("template_action_uuid")
            deleted = delete_template_action(template_action_uuid)
            return Response(data={"deleted": deleted})
        except PermissionDenied:
            return Response(status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"Error": str(e)})

    def update(self, request, *args, **kwargs):
        try:
            authorization_header = request.headers.get("Authorization", "Bearer unauthorized")
            if not is_super_user(authorization_header):
                raise PermissionDenied("You has not permission to do that.")

            data = request.data
            update_dto = UpdateTemplateActionDTO(
                template_action_uuid=kwargs.get("template_action_uuid"),
                name=data.get("name"),
                prompt=data.get("prompt"),
                action_type=data.get("action_type"),
                group=data.get("group"),
                display_prompt=data.get("display_prompt"),
            )
            usecase = UpdateTemplateActionUseCase()
            template_action = usecase.update_template_action(update_dto)
            serializer = self.get_serializer(template_action)
            return Response(data=serializer.data)
        except PermissionDenied:
            return Response(status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"Error": str(e)})
