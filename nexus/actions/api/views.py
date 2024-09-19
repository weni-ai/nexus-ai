import os
from typing import Dict, List

from django.conf import settings
from django.core.exceptions import PermissionDenied

from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from nexus.actions.models import Flow, TemplateAction
from nexus.actions.api.serializers import FlowSerializer, TemplateActionSerializer

from nexus.usecases import projects
from nexus.usecases.logs.create import CreateLogUsecase
from nexus.usecases.actions.list import ListFlowsUseCase, ListTemplateActionUseCase
from nexus.usecases.actions.create import (
    CreateFlowDTO,
    CreateFlowsUseCase,
    GenerateFlowNameUseCase,
    CreateTemplateActionUseCase
)
from nexus.usecases.actions.delete import (
    DeleteFlowsUseCase,
    DeleteFlowDTO,
    delete_template_action
)
from nexus.usecases.actions.update import (
    UpdateFlowsUseCase,
    UpdateFlowDTO,
    UpdateTemplateActionDTO,
    UpdateTemplateActionUseCase
)
from nexus.usecases.actions.retrieve import RetrieveFlowsUseCase, FlowDoesNotExist
from nexus.usecases.intelligences.exceptions import IntelligencePermissionDenied
from nexus.usecases.intelligences.get_by_uuid import get_llm_by_project_uuid
from nexus.usecases.intelligences.retrieve import get_file_info
from nexus.usecases.actions.retrieve import get_flow_by_action_type

from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase

from nexus.intelligences.llms.client import LLMClient

from nexus.orgs.permissions import is_super_user
from nexus.projects.permissions import has_project_permission
from nexus.projects.exceptions import ProjectAuthorizationDenied

from router.repositories.orm import (
    ContentBaseORMRepository,
    FlowsORMRepository,
    MessageLogsRepository
)
from router.classifiers.zeroshot import ZeroshotClassifier
# from router.classifiers.chatgpt_function import ChatGPTFunctionClassifier, OpenAIClient
from router.classifiers import classify
from router.tasks.tasks import safety_check, direct_flows
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

    def get_queryset(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            return Flow.objects.none()  # pragma: no cover
        super().get_serializer(*args, **kwargs)

    def create(self, request, *args, **kwargs):
        try:
            project_uuid = kwargs.get('project_uuid')
            project = projects.get_project_by_uuid(project_uuid)
            user = request.user

            has_project_permission(
                user=user,
                project=project,
                method="post"
            )

            flow_uuid = request.data.get("uuid")
            fallback = request.data.get("fallback")

            action_template_uuid = request.data.get("action_template_uuid", None)

            name = request.data.get("name")
            prompt = request.data.get("prompt", "")
            action_type = request.data.get("action_type", "custom")
            group = request.data.get("group", "custom")

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
                action_type=action_type,
                template=template if action_template_uuid else None,
                group=group
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
            flow_uuid = kwargs.get('flow_uuid')
            project_uuid = kwargs.get('project_uuid')
            project = projects.get_project_by_uuid(project_uuid)
            user = request.user

            has_project_permission(
                user=user,
                project=project,
                method="get"
            )

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
            project = projects.get_project_by_uuid(project_uuid)
            user = request.user

            has_project_permission(
                user=user,
                project=project,
                method="get"
            )

            flows = ListFlowsUseCase().list_flows_by_project_uuid(project_uuid)
            data = FlowSerializer(flows, many=True).data
            return Response(data=data, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def update(self, request, *args, **kwargs):
        flow_dto = UpdateFlowDTO(
            flow_uuid=kwargs.get("flow_uuid"),
            prompt=request.data.get("prompt"),
            name=request.data.get("name"),
        )
        project_uuid = kwargs.get('project_uuid')
        project = projects.get_project_by_uuid(project_uuid)
        user = request.user

        has_project_permission(
            user=user,
            project=project,
            method="put"
        )

        flow = UpdateFlowsUseCase().update_flow(
            flow_dto=flow_dto,
            user=user
        )
        data = FlowSerializer(flow).data
        return Response(data=data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        try:
            project_uuid = kwargs.get('project_uuid')
            flow_dto = DeleteFlowDTO(
                flow_uuid=kwargs.get("flow_uuid"),
            )
            project = projects.get_project_by_uuid(project_uuid)
            user = request.user

            has_project_permission(
                user=user,
                project=project,
                method="delete"
            )

            DeleteFlowsUseCase().hard_delete_flow(
                flow_dto=flow_dto,
                user=user,
                project=project
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        except FlowDoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


class MessagePreviewView(APIView):

    # TODO: Refactor this method to put the logic in a usecase/observers
    def post(self, request, *args, **kwargs):
        try:
            data = request.data

            project_uuid = kwargs.get("project_uuid")
            text = data.get("text")
            contact_urn = data.get("contact_urn")

            project = projects.get_project_by_uuid(project_uuid)

            has_project_permission(
                user=request.user,
                project=project,
                method="post"
            )

            log_usecase = CreateLogUsecase()
            log_usecase.create_message_log(text, contact_urn)

            flows_repository = FlowsORMRepository()
            content_base_repository = ContentBaseORMRepository()
            message_logs_repository = MessageLogsRepository()

            message = Message(
                project_uuid=project_uuid,
                text=text,
                contact_urn=contact_urn,
            )

            print(f"[+ Message: {message.text} - Contact: {message.contact_urn} - Project: {message.project_uuid} +]")

            project_uuid: str = message.project_uuid

            flows: List[FlowDTO] = flows_repository.project_flows(
                project_uuid=project_uuid,
                fallback=False,
                action_type="custom"
            )

            content_base: ContentBaseDTO = content_base_repository.get_content_base_by_project(message.project_uuid)

            agent: AgentDTO = content_base_repository.get_agent(content_base.uuid)
            agent = agent.set_default_if_null()

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
                language=llm_model.setup.get("language", settings.WENIGPT_DEFAULT_LANGUAGE)
            )

            print(f"[+ LLM model: {llm_config.model}:{llm_config.model_version} +]")

            # if llm_config.model.lower() == "chatgpt":
            #     client = OpenAIClient(api_key=llm_config.token)
            #     classifier = ChatGPTFunctionClassifier(
            #         client=client,
            #         chatgpt_model=llm_config.model_version,
            #     )
            # else:
            classifier = ZeroshotClassifier(
                chatbot_goal=agent.goal
            )
            broadcast = SimulateBroadcast(os.environ.get('FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_INTERNAL_TOKEN'), get_file_info)
            flow_start = SimulateFlowStart(os.environ.get('FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_INTERNAL_TOKEN'))
            flows_user_email = os.environ.get("FLOW_USER_EMAIL")

            # TODO - Refactor direct_flows to return formated response, or create a new method for that API
            if not safety_check(message.text):
                try:
                    if direct_flows(
                        content_base=content_base,
                        message=message,
                        msg_event={},
                        flow_start=flow_start,
                        user_email=flows_user_email,
                        action_type="safe_guard"
                    ):
                        flow = get_flow_by_action_type(
                            content_base_uuid=content_base.uuid,
                            action_type="safe_guard"
                        )
                        return Response({
                            "type": "flowstart",
                            "uuid": flow.uuid,
                            "name": flow.name,
                            "msg_event": None
                        })
                except FlowDoesNotExist as e:
                    print(f"[- START ROUTE - Error: {e} -]")

            classification = classify(
                classifier=classifier,
                message=message.text,
                flows=flows,
                language=llm_config.language
            )

            llm_client = LLMClient.get_by_type(llm_config.model)
            llm_client: LLMClient = list(llm_client)[0](model_version=llm_config.model_version)

            if llm_config.model.lower() != "wenigpt":
                llm_client.api_key = llm_config.token

            print(f"[+ Classfication: {classification} +]")

            response: dict = route(
                classification=classification,
                message=message,
                content_base_repository=content_base_repository,
                flows_repository=flows_repository,
                message_logs_repository=message_logs_repository,
                indexer=SentenXFileDataBase(),
                llm_client=llm_client,
                direct_message=broadcast,
                flow_start=flow_start,
                llm_config=llm_config,
                flows_user_email=flows_user_email,
                log_usecase=log_usecase,
            )

            log_usecase.update_status("S")

            return Response(data=response)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


class GenerateActionNameView(APIView):
    def post(self, request, *args, **kwargs):
        try:
            user = request.user
            project = projects.get_project_by_uuid(kwargs.get("project_uuid"))
            has_project_permission(
                method="post",
                user=user,
                project=project
            )

            data = request.data
            chatbot_goal = data.get("chatbot_goal")
            context = data.get("context")

            usecase = GenerateFlowNameUseCase()
            response = usecase.generate_action_name(chatbot_goal, context)
            return Response(data=response)
        except ProjectAuthorizationDenied:
            return Response(status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                data={"Error": str(e)}
            )


class TemplateActionView(ModelViewSet):
    serializer_class = TemplateActionSerializer

    def get_queryset(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            return TemplateAction.objects.none()  # pragma: no cover
        super().get_serializer(*args, **kwargs)

    def list(self, request, *args, **kwargs):
        try:
            language = request.query_params.get("language", "pt-br")
            user = request.user
            project = projects.get_project_by_uuid(kwargs.get("project_uuid"))
            has_project_permission(
                method="get",
                user=user,
                project=project
            )

            template_actions = ListTemplateActionUseCase().list_template_action(
                language=language
            )
            serializer = self.get_serializer(template_actions, many=True)
            return Response(data=serializer.data)
        except ProjectAuthorizationDenied:
            return Response(status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                data={"Error": str(e)}
            )

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
                name=name,
                prompt=prompt,
                action_type=action_type,
                group=group,
                display_prompt=display_prompt
            )
            serializer = self.get_serializer(template_action)
            return Response(data=serializer.data)
        except PermissionDenied:
            return Response(status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                data={"Error": str(e)}
            )

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
            return Response(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                data={"Error": str(e)}
            )

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
                display_prompt=data.get("display_prompt")
            )
            usecase = UpdateTemplateActionUseCase()
            template_action = usecase.update_template_action(update_dto)
            serializer = self.get_serializer(template_action)
            return Response(data=serializer.data)
        except PermissionDenied:
            return Response(status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                data={"Error": str(e)}
            )
