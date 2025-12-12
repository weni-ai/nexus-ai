import os

import sentry_sdk
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils.datastructures import MultiValueDictKeyError
from django_filters import rest_framework as filters
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import parsers, status, views
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from nexus.authentication import AUTHENTICATION_CLASSES
from nexus.events import event_manager
from nexus.intelligences.api.filters import ConversationFilter
from nexus.intelligences.models import (
    ContentBase,
    ContentBaseFile,
    ContentBaseLink,
    ContentBaseText,
    Conversation,
    Intelligence,
    SubTopics,
    Topics,
)
from nexus.orgs import permissions
from nexus.paginations import CustomCursorPagination, SupervisorPagination
from nexus.projects.api.permissions import CombinedExternalProjectPermission, ProjectPermission
from nexus.projects.exceptions import ProjectDoesNotExist
from nexus.projects.models import Project
from nexus.storage import AttachmentPreviewStorage, validate_mime_type
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
from nexus.task_managers.file_database.s3_file_database import s3FileDatabase
from nexus.task_managers.file_database.sentenx_file_database import (
    SentenXDocumentPreview,
    SentenXFileDataBase,
)
from nexus.task_managers.file_manager.celery_file_manager import (
    CeleryFileManager,
)
from nexus.task_managers.models import ContentBaseFileTaskManager
from nexus.task_managers.tasks import (
    delete_file_task,
    send_link,
    upload_text_file,
)
from nexus.task_managers.tasks_bedrock import (
    bedrock_send_link,
    bedrock_upload_text_file,
    start_ingestion_job,
)
from nexus.usecases import intelligences
from nexus.usecases.intelligences.exceptions import (
    ContentBaseDoesNotExist,
    IntelligencePermissionDenied,
)
from nexus.usecases.intelligences.get_by_uuid import (
    get_default_content_base_by_project,
)
from nexus.usecases.orgs.get_by_uuid import get_org_by_content_base_uuid
from nexus.usecases.projects.get_by_uuid import get_project_by_uuid
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from nexus.usecases.task_managers.celery_task_manager import (
    CeleryTaskManagerUseCase,
)
from nexus.usecases.task_managers.file_database import (
    get_gpt_by_content_base_uuid,
)
from nexus.usecases.users.exceptions import UserDoesNotExists
from nexus.users.models import User

from .serializers import (
    ContentBaseFileSerializer,
    ContentBaseLinkSerializer,
    ContentBasePersonalizationSerializer,
    ContentBaseSerializer,
    ContentBaseTextSerializer,
    CreatedContentBaseLinkSerializer,
    InstructionClassificationRequestSerializer,
    InstructionClassificationResponseSerializer,
    IntelligenceSerializer,
    LLMConfigSerializer,
    RouterContentBaseSerializer,
    SubTopicsSerializer,
    SupervisorDataSerializer,
    TopicsSerializer,
)


class IntelligencesViewset(ModelViewSet):
    serializer_class = IntelligenceSerializer
    pagination_class = CustomCursorPagination

    permission_classes = [IsAuthenticated]

    def validate_kwargs(self, kwargs: dict):
        if kwargs.get("pk"):
            return
        return Response(status=status.HTTP_400_BAD_REQUEST)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Intelligence.objects.none()  # pragma: no cover
        user_email = self.request.user.email
        use_case = intelligences.ListIntelligencesUseCase()
        org_uuid = self.kwargs.get("org_uuid")
        use_case_list = use_case.get_org_intelligences(org_uuid, user_email=user_email)

        return use_case_list

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def retrieve(self, request, *args, **kwargs):
        self.validate_kwargs(kwargs)
        try:
            user_email = request.user.email
            intelligence_uuid = kwargs.get("pk")
            use_case = intelligences.RetrieveIntelligenceUseCase()
            intelligence = use_case.get_intelligence(intelligence_uuid=intelligence_uuid, user_email=user_email)
            serializer = IntelligenceSerializer(intelligence)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def create(
        self,
        request,
        org_uuid=str,
    ):
        try:
            user_email = request.user.email
            use_case = intelligences.CreateIntelligencesUseCase()

            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            name = serializer.validated_data.get("name")
            description = serializer.validated_data.get("description")

            intelligence = use_case.create_intelligences(
                org_uuid=org_uuid, name=name, description=description, user_email=user_email
            )

            return Response(IntelligenceSerializer(intelligence).data, status=status.HTTP_201_CREATED)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def update(self, request, *args, **kwargs):
        self.validate_kwargs(kwargs)
        try:
            user_email = request.user.email
            use_case = intelligences.UpdateIntelligenceUseCase()

            update_intelligence = use_case.update_intelligences(
                intelligence_uuid=kwargs.get("pk"),
                name=request.data.get("name"),
                description=request.data.get("description"),
                user_email=user_email,
            )

            return Response(IntelligenceSerializer(update_intelligence).data, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def destroy(self, request, **kwargs):
        self.validate_kwargs(kwargs)
        try:
            user_email = request.user.email
            use_case = intelligences.DeleteIntelligenceUseCase()

            intelligence_uuid = kwargs.get("pk")

            use_case.delete_intelligences(intelligence_uuid=intelligence_uuid, user_email=user_email)

            return Response(status=status.HTTP_204_NO_CONTENT)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


class FlowsIntelligencesApiView(views.APIView):
    authentication_classes = []

    def get(self, request, project_uuid):
        authorization_header = request.headers.get("Authorization", "Bearer unauthorized")

        is_super_user = permissions.is_super_user(authorization_header)

        if not is_super_user:
            raise PermissionDenied("You do not have permission to perform this action.")

        list_use_case = intelligences.ListAllIntelligenceContentUseCase()
        return Response(
            data=list_use_case.get_project_intelligences(project_uuid=project_uuid, is_super_user=is_super_user),
            status=200,
        )


class GenerativeIntelligenceQuestionAPIView(views.APIView):
    authentication_classes = []

    def post(self, request):
        authorization_header = request.headers.get("Authorization", "Bearer unauthorized")

        if not permissions.is_super_user(authorization_header):
            raise PermissionDenied("You do not have permission to perform this action.")

        data = request.data

        custom_rules_content_base_uuid = os.environ.get("CUSTOM_RULES_CONTENT_BASE_UUID")

        content_base_uuid = data.get("content_base_uuid")
        generative_ai_database = get_gpt_by_content_base_uuid(content_base_uuid)

        db = SentenXFileDataBase() if content_base_uuid != custom_rules_content_base_uuid else BedrockFileDatabase()

        intelligence_usecase = intelligences.IntelligenceGenerativeSearchUseCase(
            search_file_database=db, generative_ai_database=generative_ai_database
        )
        data = intelligence_usecase.search(
            content_base_uuid=content_base_uuid, text=data.get("text"), language=data.get("language")
        )
        if data.get("answers"):
            return Response(data=data, status=200)
        return Response(status=404, data={"message": data.get("message")})


class QuickTestAIAPIView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            data = request.data
            content_base_uuid = data.get("content_base_uuid")

            user = request.user
            org = get_org_by_content_base_uuid(content_base_uuid)
            has_permission = permissions.can_list_content_bases(user, org)

            custom_rules_content_base_uuid = os.environ.get("CUSTOM_RULES_CONTENT_BASE_UUID")

            db = SentenXFileDataBase() if content_base_uuid != custom_rules_content_base_uuid else BedrockFileDatabase()

            if has_permission:
                generative_ai_database = get_gpt_by_content_base_uuid(content_base_uuid)

                intelligence_usecase = intelligences.IntelligenceGenerativeSearchUseCase(
                    search_file_database=db,
                    generative_ai_database=generative_ai_database,
                    testing=True,
                )

                return Response(
                    data=intelligence_usecase.search(
                        content_base_uuid=content_base_uuid,
                        text=data.get("text"),
                        language=data.get("language", "pt-br"),
                    ),
                    status=200,
                )
            raise IntelligencePermissionDenied()
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


class SentenxIndexerUpdateFile(views.APIView):
    authentication_classes = []

    def patch(self, request):
        authorization_header = request.headers.get("Authorization", "Bearer unauthorized")
        if not permissions.is_super_user(authorization_header):
            raise PermissionDenied("You has not permission to do that.")
        data = request.data
        task_manager_usecase = CeleryTaskManagerUseCase()
        sentenx_status = [ContentBaseFileTaskManager.STATUS_FAIL, ContentBaseFileTaskManager.STATUS_SUCCESS]
        task_manager_usecase.update_task_status(
            task_uuid=data.get("task_uuid"), status=sentenx_status[data.get("status")], file_type=data.get("file_type")
        )
        return Response(status=200, data=data)


class ContentBaseViewset(ModelViewSet):
    pagination_class = CustomCursorPagination
    serializer_class = ContentBaseSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "contentbase_uuid"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContentBase.objects.none()  # pragma: no cover
        user_email = self.request.user.email
        use_case = intelligences.ListContentBaseUseCase()
        intelligence_uuid = self.kwargs.get("intelligence_uuid")
        use_case_list = use_case.get_intelligence_contentbases(intelligence_uuid, user_email=user_email)
        return use_case_list

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def retrieve(self, request, *args, **kwargs):
        try:
            user_email = request.user.email
            use_case = intelligences.RetrieveContentBaseUseCase()
            contentbase = use_case.get_contentbase(
                contentbase_uuid=kwargs.get("contentbase_uuid"), user_email=user_email
            )
            serializer = ContentBaseSerializer(contentbase)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def create(
        self,
        request,
        intelligence_uuid=str,
    ):
        try:
            user_email = request.user.email
            use_case = intelligences.CreateContentBaseUseCase()

            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            title = serializer.validated_data.get("title")
            description = serializer.validated_data.get("description")
            language = serializer.validated_data.get("language")

            contentbase = use_case.create_contentbase(
                intelligence_uuid=intelligence_uuid,
                title=title,
                user_email=user_email,
                description=description,
                language=language,
            )

            return Response(ContentBaseSerializer(contentbase).data, status=status.HTTP_201_CREATED)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def update(self, request, intelligence_uuid: str, **kwargs):
        try:
            user_email = request.user.email
            use_case = intelligences.UpdateContentBaseUseCase()

            update_contentbase = use_case.update_contentbase(
                contentbase_uuid=kwargs.get("contentbase_uuid"),
                title=request.data.get("title"),
                language=request.data.get("language"),
                description=request.data.get("description"),
                user_email=user_email,
            )

            return Response(ContentBaseSerializer(update_contentbase).data, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def destroy(self, request, intelligence_uuid: str, **kwargs):
        try:
            user_email = request.user.email
            use_case = intelligences.DeleteContentBaseUseCase()

            contentbase_uuid = kwargs.get("contentbase_uuid")

            use_case.delete_contentbase(contentbase_uuid=contentbase_uuid, user_email=user_email)

            return Response(status=status.HTTP_204_NO_CONTENT)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


class ContentBaseTextViewset(ModelViewSet):
    pagination_class = CustomCursorPagination
    serializer_class = ContentBaseTextSerializer
    lookup_url_kwarg = "contentbasetext_uuid"
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContentBaseText.objects.none()  # pragma: no cover
        user_email = self.request.user.email
        use_case = intelligences.ListContentBaseTextUseCase()
        contentbase_uuid = self.kwargs.get("content_base_uuid")
        use_case_list = use_case.get_contentbase_contentbasetexts(contentbase_uuid, user_email=user_email)
        return use_case_list

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def retrieve(self, request, *args, **kwargs):
        try:
            user_email = request.user.email
            contentbasetext_uuid = kwargs.get("contentbasetext_uuid")

            use_case = intelligences.RetrieveContentBaseTextUseCase()
            contentbasetext = use_case.get_contentbasetext(
                contentbasetext_uuid=contentbasetext_uuid, user_email=user_email
            )

            serializer = ContentBaseTextSerializer(contentbasetext)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def create(self, request, content_base_uuid: str):
        try:
            user_email = request.user.email

            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            text = serializer.validated_data.get("text")
            content_base = intelligences.get_by_contentbase_uuid(content_base_uuid)
            cb_dto = intelligences.ContentBaseDTO(
                uuid=content_base.uuid,
                title=content_base.title,
                intelligence_uuid=content_base.intelligence.uuid,
                created_by_email=content_base.created_by.email,
            )
            cbt_dto = intelligences.ContentBaseTextDTO(
                text=text, content_base_uuid=content_base_uuid, user_email=user_email
            )
            content_base_text = intelligences.CreateContentBaseTextUseCase().create_contentbasetext(
                content_base_dto=cb_dto, content_base_text_dto=cbt_dto
            )
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
            if project.indexer_database == Project.BEDROCK:
                bedrock_upload_text_file.delay(
                    content_base_dto=cb_dto.__dict__, content_base_text_uuid=str(content_base_text.uuid), text=text
                )

            else:
                upload_text_file.delay(
                    content_base_dto=cb_dto.__dict__, content_base_text_uuid=content_base_text.uuid, text=text
                )

            response = ContentBaseTextSerializer(content_base_text).data

            return Response(response, status=status.HTTP_201_CREATED)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except ObjectDoesNotExist:
            upload_text_file.delay(
                content_base_dto=cb_dto.__dict__, content_base_text_uuid=content_base_text.uuid, text=text
            )
            response = ContentBaseTextSerializer(content_base_text).data

            return Response(response, status=status.HTTP_201_CREATED)

    def update(self, request, **kwargs):
        try:
            user_email = request.user.email
            text = request.data.get("text")
            content_base_uuid = kwargs.get("content_base_uuid")
            content_base_text_uuid = kwargs.get("contentbasetext_uuid")
            content_base = intelligences.get_by_contentbase_uuid(content_base_uuid)
            content_base_text = intelligences.get_by_contentbasetext_uuid(content_base_text_uuid)
            cb_dto = intelligences.ContentBaseDTO(
                uuid=content_base.uuid,
                title=content_base.title,
                intelligence_uuid=content_base.intelligence.uuid,
                created_by_email=content_base.created_by.email,
            )
            content_base_text = intelligences.UpdateContentBaseTextUseCase().update_contentbasetext(
                contentbasetext=content_base_text, user_email=user_email, text=text
            )
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
            file_database = ProjectsUseCase().get_indexer_database_by_project(project)

            delete_use_case = intelligences.DeleteContentBaseTextUseCase(file_database())
            delete_use_case.delete_content_base_text_from_index(
                content_base_text_uuid, content_base_uuid, content_base_text.file_name
            )

            if project.indexer_database == Project.BEDROCK:
                bedrock_upload_text_file.delay(
                    content_base_dto=cb_dto.__dict__, content_base_text_uuid=str(content_base_text.uuid), text=text
                )
            else:
                upload_text_file.delay(
                    content_base_dto=cb_dto.__dict__,
                    content_base_text_uuid=content_base_text.uuid,
                    text=text,
                )

            response = ContentBaseTextSerializer(content_base_text).data

            return Response(response, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except ObjectDoesNotExist:
            file_database = SentenXFileDataBase
            delete_use_case = intelligences.DeleteContentBaseTextUseCase(file_database())
            delete_use_case.delete_content_base_text_from_index(
                content_base_text_uuid, content_base_uuid, content_base_text.file_name
            )
            upload_text_file.delay(
                content_base_dto=cb_dto.__dict__,
                content_base_text_uuid=content_base_text.uuid,
                text=text,
            )
            response = ContentBaseTextSerializer(content_base_text).data
            return Response(response, status=status.HTTP_200_OK)

    def destroy(self, request, **kwargs):
        try:
            user_email = request.user.email
            content_base_uuid = kwargs.get("content_base_uuid")
            project_use_case = ProjectsUseCase()
            project = project_use_case.get_project_by_content_base_uuid(content_base_uuid)
            indexer = project_use_case.get_indexer_database_by_project(project)
            use_case = intelligences.DeleteContentBaseTextUseCase(indexer())

            contentbasetext_uuid = kwargs.get("contentbasetext_uuid")
            use_case.delete_contentbasetext(contentbasetext_uuid=contentbasetext_uuid, user_email=user_email)

            return Response(status=status.HTTP_204_NO_CONTENT)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except ObjectDoesNotExist:
            indexer = SentenXFileDataBase
            use_case = intelligences.DeleteContentBaseTextUseCase(indexer())

            contentbasetext_uuid = kwargs.get("contentbasetext_uuid")
            use_case.delete_contentbasetext(contentbasetext_uuid=contentbasetext_uuid, user_email=user_email)
            return Response(status=status.HTTP_204_NO_CONTENT)


class InlineContentBaseTextViewset(ModelViewSet):
    pagination_class = CustomCursorPagination
    serializer_class = ContentBaseTextSerializer
    lookup_url_kwarg = "contentbasetext_uuid"
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContentBaseText.objects.none()  # pragma: no cover
        use_case = intelligences.ListContentBaseTextUseCase()
        project_uuid = self.kwargs.get("project_uuid")
        content_base_text_objects = use_case.get_inline_contentbasetext(
            project_uuid,
        )
        return content_base_text_objects

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def retrieve(self, request, *args, **kwargs):
        try:
            project_uuid = kwargs.get("project_uuid")

            use_case = intelligences.RetrieveContentBaseTextUseCase()
            contentbasetext = use_case.get_inline_contentbasetext(
                project_uuid=project_uuid,
            )

            serializer = ContentBaseTextSerializer(contentbasetext)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def create(self, request, project_uuid: str):
        try:
            user_email = request.user.email

            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            text = serializer.validated_data.get("text")
            content_base = intelligences.get_default_content_base_by_project(project_uuid)
            cb_dto = intelligences.ContentBaseDTO(
                uuid=content_base.uuid,
                title=content_base.title,
                intelligence_uuid=content_base.intelligence.uuid,
                created_by_email=content_base.created_by.email,
            )
            cbt_dto = intelligences.ContentBaseTextDTO(
                text=text, content_base_uuid=content_base.uuid, user_email=user_email
            )
            content_base_text = intelligences.CreateContentBaseTextUseCase().create_contentbasetext(
                content_base_dto=cb_dto, content_base_text_dto=cbt_dto
            )
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base.uuid)
            if project.indexer_database == Project.BEDROCK:
                bedrock_upload_text_file.delay(
                    content_base_dto=cb_dto.__dict__, content_base_text_uuid=str(content_base_text.uuid), text=text
                )

            else:
                upload_text_file.delay(
                    content_base_dto=cb_dto.__dict__, content_base_text_uuid=content_base_text.uuid, text=text
                )

            response = ContentBaseTextSerializer(content_base_text).data

            return Response(response, status=status.HTTP_201_CREATED)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except ObjectDoesNotExist:
            upload_text_file.delay(
                content_base_dto=cb_dto.__dict__, content_base_text_uuid=content_base_text.uuid, text=text
            )
            response = ContentBaseTextSerializer(content_base_text).data

            return Response(response, status=status.HTTP_201_CREATED)

    def update(self, request, **kwargs):
        try:
            user_email = request.user.email
            text = request.data.get("text")
            project_uuid = kwargs.get("project_uuid")

            content_base = intelligences.get_default_content_base_by_project(project_uuid)
            content_base_uuid = content_base.uuid
            content_base_text_uuid = kwargs.get("contentbasetext_uuid")
            content_base_text = intelligences.get_by_contentbasetext_uuid(content_base_text_uuid)
            cb_dto = intelligences.ContentBaseDTO(
                uuid=content_base.uuid,
                title=content_base.title,
                intelligence_uuid=content_base.intelligence.uuid,
                created_by_email=content_base.created_by.email,
            )
            content_base_text = intelligences.UpdateContentBaseTextUseCase().update_inline_contentbasetext(
                contentbasetext=content_base_text, user_email=user_email, text=text
            )
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base.uuid)
            file_database = ProjectsUseCase().get_indexer_database_by_project(project)

            delete_use_case = intelligences.DeleteContentBaseTextUseCase(file_database())
            delete_use_case.delete_content_base_text_from_index(
                content_base_text_uuid, content_base_uuid, content_base_text.file_name
            )

            if project.indexer_database == Project.BEDROCK:
                bedrock_upload_text_file.delay(
                    content_base_dto=cb_dto.__dict__, content_base_text_uuid=str(content_base_text.uuid), text=text
                )
            else:
                upload_text_file.delay(
                    content_base_dto=cb_dto.__dict__,
                    content_base_text_uuid=content_base_text.uuid,
                    text=text,
                )

            response = ContentBaseTextSerializer(content_base_text).data

            return Response(response, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except ObjectDoesNotExist:
            file_database = SentenXFileDataBase
            delete_use_case = intelligences.DeleteContentBaseTextUseCase(file_database())
            delete_use_case.delete_content_base_text_from_index(
                content_base_text_uuid, content_base_uuid, content_base_text.file_name
            )
            upload_text_file.delay(
                content_base_dto=cb_dto.__dict__,
                content_base_text_uuid=content_base_text.uuid,
                text=text,
            )
            response = ContentBaseTextSerializer(content_base_text).data
            return Response(response, status=status.HTTP_200_OK)

    def destroy(self, request, **kwargs):
        try:
            project_uuid = kwargs.get("project_uuid")
            content_base = intelligences.get_default_content_base_by_project(project_uuid)
            project_use_case = ProjectsUseCase()
            project = project_use_case.get_project_by_content_base_uuid(content_base.uuid)
            indexer = project_use_case.get_indexer_database_by_project(project)
            use_case = intelligences.DeleteContentBaseTextUseCase(indexer())

            contentbasetext_uuid = kwargs.get("contentbasetext_uuid")
            use_case.delete_inline_contentbasetext(
                contentbasetext_uuid=contentbasetext_uuid,
            )

            return Response(status=status.HTTP_204_NO_CONTENT)
        except ObjectDoesNotExist:
            indexer = SentenXFileDataBase
            use_case = intelligences.DeleteContentBaseTextUseCase(indexer())

            contentbasetext_uuid = kwargs.get("contentbasetext_uuid")
            use_case.delete_inline_contentbasetext(
                contentbasetext_uuid=contentbasetext_uuid,
            )
            return Response(status=status.HTTP_204_NO_CONTENT)


class ContentBaseFileViewset(ModelViewSet):
    serializer_class = ContentBaseFileSerializer
    pagination_class = CustomCursorPagination
    parser_classes = (parsers.MultiPartParser,)
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "contentbase_file_uuid"

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def create(self, request, **kwargs):
        from rest_framework import status as http_status

        def validate_file_size(file):
            # default 50 MiB
            if file.size > (settings.BEDROCK_FILE_SIZE_LIMIT * (1024**2)):
                return Response(data={"message": "File size is too large"}, status=http_status.HTTP_400_BAD_REQUEST)

        try:
            # Get content_base_uuid from URL kwargs
            content_base_uuid = self.kwargs.get("content_base_uuid")
            if not content_base_uuid:
                return Response(
                    data={"message": "content_base_uuid is required"}, status=http_status.HTTP_400_BAD_REQUEST
                )

            # Check permissions by calling get_queryset
            self.get_queryset()

            user: User = request.user
            file: InMemoryUploadedFile = request.FILES["file"]
            validate_file_size(file)
            user_email: str = user.email
            extension_file: str = request.data.get("extension_file")
            load_type = request.data.get("load_type")

            file_manager = CeleryFileManager()

            try:
                project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
                indexer_database = project.indexer_database
            except ObjectDoesNotExist:
                indexer_database = Project.SENTENX

            if indexer_database == Project.BEDROCK:
                data, status = file_manager.upload_and_ingest_file(
                    file,
                    file.name,
                    content_base_uuid,
                    extension_file,
                    user_email,
                )
                return Response(data=data, status=status)

            # will be removed in the future
            response = file_manager.upload_file(
                file, content_base_uuid, extension_file, user_email, load_type, filename=file.name
            )

            return Response(response, status=http_status.HTTP_201_CREATED)

        except MultiValueDictKeyError:
            return Response(data={"message": "file is required"}, status=http_status.HTTP_400_BAD_REQUEST)
        except IntelligencePermissionDenied:
            return Response(status=http_status.HTTP_401_UNAUTHORIZED)
        except ContentBaseDoesNotExist as e:
            return Response(data={"message": str(e)}, status=http_status.HTTP_404_NOT_FOUND)
        except UserDoesNotExists as e:
            return Response(data={"message": str(e)}, status=http_status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            return Response(data={"message": f"Invalid UUID: {str(e)}"}, status=http_status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            return Response(
                data={"message": f"An error occurred while uploading the file: {str(e)}"},
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContentBaseFile.objects.none()  # pragma: no cover
        use_case = intelligences.ListContentBaseFileUseCase()
        contentbase_uuid = self.kwargs.get("content_base_uuid")
        return use_case.get_contentbase_file(contentbase_uuid=contentbase_uuid, user_email=self.request.user.email)

    def retrieve(self, request, *args, **kwargs):
        try:
            user_email: str = self.request.user.email
            contentbasefile_uuid: str = kwargs.get("contentbase_file_uuid")
            use_case = intelligences.RetrieveContentBaseFileUseCase()
            contentbasetext = use_case.get_contentbasefile(
                contentbasefile_uuid=contentbasefile_uuid, user_email=user_email
            )
            serializer = self.get_serializer(contentbasetext)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def destroy(self, request, *args, **kwargs):
        try:
            user_email: str = self.request.user.email
            contentbasefile_uuid: str = kwargs.get("contentbase_file_uuid")
            content_base_uuid: str = kwargs.get("content_base_uuid")
            use_case = intelligences.RetrieveContentBaseFileUseCase()
            content_base_file = use_case.get_contentbasefile(
                contentbasefile_uuid=contentbasefile_uuid, user_email=user_email
            )
            project_use_case = ProjectsUseCase()
            project = project_use_case.get_project_by_content_base_uuid(content_base_uuid)
            indexer = project_use_case.get_indexer_database_by_project(project)
            intelligences.DeleteContentBaseFileUseCase(indexer).delete_by_object(content_base_file)

            if project.indexer_database == Project.BEDROCK:
                start_ingestion_job.delay("", post_delete=True, project_uuid=str(project.uuid))

            event_manager.notify(
                event="contentbase_file_activity",
                action_type="D",
                content_base_file=content_base_file,
                user=self.request.user,
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ObjectDoesNotExist:
            indexer = SentenXFileDataBase
            intelligences.DeleteContentBaseFileUseCase(indexer).delete_by_object(content_base_file)
            event_manager.notify(
                event="contentbase_file_activity",
                action_type="D",
                content_base_file=content_base_file,
                user=self.request.user,
            )
            return Response(status=status.HTTP_204_NO_CONTENT)


class InlineContentBaseFileViewset(ModelViewSet):
    serializer_class = ContentBaseFileSerializer
    pagination_class = CustomCursorPagination
    parser_classes = (parsers.MultiPartParser,)
    permission_classes = [IsAuthenticated, ProjectPermission]
    lookup_url_kwarg = "contentbase_file_uuid"

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def create(self, request, **kwargs):
        from rest_framework import status as http_status

        def validate_file_size(file):
            # default 50 MiB
            if file.size > (settings.BEDROCK_FILE_SIZE_LIMIT * (1024**2)):
                return Response(data={"message": "File size is too large"}, status=http_status.HTTP_400_BAD_REQUEST)

        content_base = intelligences.get_by_uuid.get_default_content_base_by_project(self.kwargs.get("project_uuid"))
        content_base_uuid = str(content_base.uuid)

        user: User = request.user
        file: InMemoryUploadedFile = request.FILES["file"]
        validate_file_size(file)
        user_email: str = user.email
        extension_file: str = request.data.get("extension_file")
        load_type = request.data.get("load_type")

        file_manager = CeleryFileManager()

        try:
            project = ProjectsUseCase().get_by_uuid(self.kwargs.get("project_uuid"))
            indexer_database = project.indexer_database
        except ObjectDoesNotExist:
            indexer_database = Project.SENTENX

        if indexer_database == Project.BEDROCK:
            data, status = file_manager.upload_and_ingest_inline_file(
                file,
                file.name,
                content_base_uuid,
                extension_file,
                user_email,
            )
            return Response(data=data, status=status)

        # will be removed in the future
        response = file_manager.upload_inline_file(
            file, content_base_uuid, extension_file, user_email, load_type, filename=file.name
        )

        return Response(response, status=http_status.HTTP_201_CREATED)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContentBaseFile.objects.none()  # pragma: no cover
        project_uuid = self.kwargs.get("project_uuid")
        content_base = intelligences.get_by_uuid.get_default_content_base_by_project(project_uuid)
        return ContentBaseFile.objects.filter(content_base=content_base)

    def retrieve(self, request, *args, **kwargs):
        contentbasefile_uuid: str = kwargs.get("contentbase_file_uuid")
        use_case = intelligences.RetrieveContentBaseFileUseCase()
        contentbasetext = use_case.get_inline_contentbase_file(contentbasefile_uuid=contentbasefile_uuid)
        serializer = self.get_serializer(contentbasetext)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        try:
            contentbasefile_uuid: str = kwargs.get("contentbase_file_uuid")

            content_base = intelligences.get_by_uuid.get_default_content_base_by_project(
                self.kwargs.get("project_uuid")
            )
            content_base_uuid = str(content_base.uuid)

            use_case = intelligences.RetrieveContentBaseFileUseCase()
            content_base_file = use_case.get_inline_contentbase_file(contentbasefile_uuid=contentbasefile_uuid)
            project_use_case = ProjectsUseCase()
            project = project_use_case.get_project_by_content_base_uuid(content_base_uuid)
            indexer = project_use_case.get_indexer_database_by_project(project)
            intelligences.DeleteContentBaseFileUseCase(indexer).delete_by_object(content_base_file)

            if project.indexer_database == Project.BEDROCK:
                start_ingestion_job.delay("", post_delete=True, project_uuid=str(project.uuid))

            event_manager.notify(
                event="contentbase_file_activity",
                action_type="D",
                content_base_file=content_base_file,
                user=self.request.user,
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ObjectDoesNotExist:
            indexer = SentenXFileDataBase
            intelligences.DeleteContentBaseFileUseCase(indexer).delete_by_object(content_base_file)
            event_manager.notify(
                event="contentbase_file_activity",
                action_type="D",
                content_base_file=content_base_file,
                user=self.request.user,
            )
            return Response(status=status.HTTP_204_NO_CONTENT)


class ContentBaseLinkViewset(ModelViewSet):
    serializer_class = ContentBaseLinkSerializer
    lookup_url_kwarg = "contentbaselink_uuid"

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContentBaseFile.objects.none()  # pragma: no cover
        use_case = intelligences.ListContentBaseLinkUseCase()
        contentbase_uuid = self.kwargs.get("content_base_uuid")
        return use_case.get_contentbase_link(contentbase_uuid=contentbase_uuid, user_email=self.request.user.email)

    def create(self, request, content_base_uuid: str):
        try:
            user_email = request.user.email
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            link = serializer.validated_data.get("link")
            content_base = intelligences.get_by_contentbase_uuid(content_base_uuid)
            link_dto = intelligences.ContentBaseLinkDTO(
                link=link, user_email=user_email, content_base_uuid=str(content_base.uuid)
            )
            content_base_link = intelligences.CreateContentBaseLinkUseCase().create_content_base_link(link_dto)
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)

            if project.indexer_database == Project.BEDROCK:
                bedrock_send_link.delay(
                    link=link, user_email=user_email, content_base_link_uuid=str(content_base_link.uuid)
                )
            else:
                send_link.delay(link=link, user_email=user_email, content_base_link_uuid=str(content_base_link.uuid))

            response = CreatedContentBaseLinkSerializer(content_base_link).data

            return Response(response, status=status.HTTP_201_CREATED)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except ObjectDoesNotExist:
            send_link.delay(link=link, user_email=user_email, content_base_link_uuid=str(content_base_link.uuid))
            response = CreatedContentBaseLinkSerializer(content_base_link).data
            return Response(response, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        try:
            user = self.request.user
            user_email: str = user.email
            contentbaselink_uuid: str = kwargs.get("contentbaselink_uuid")
            content_base_uuid: str = kwargs.get("content_base_uuid")

            use_case = intelligences.RetrieveContentBaseLinkUseCase()
            content_base_link = use_case.get_contentbaselink(
                contentbaselink_uuid=contentbaselink_uuid, user_email=user_email
            )
            project_use_case = ProjectsUseCase()
            project = project_use_case.get_project_by_content_base_uuid(content_base_uuid)
            indexer = project_use_case.get_indexer_database_by_project(project)

            use_case = intelligences.DeleteContentBaseLinkUseCase(indexer)
            use_case.delete_by_object(
                content_base_link,
            )

            if project.indexer_database == Project.BEDROCK:
                start_ingestion_job.delay("", post_delete=True, project_uuid=str(project.uuid))

            event_manager.notify(
                event="contentbase_link_activity", action_type="D", content_base_link=content_base_link, user=user
            )

            return Response(status=status.HTTP_204_NO_CONTENT)
        except ObjectDoesNotExist:
            indexer = SentenXFileDataBase
            use_case = intelligences.DeleteContentBaseLinkUseCase(indexer)
            use_case.delete_by_object(
                content_base_link,
            )
            event_manager.notify(
                event="contentbase_link_activity", action_type="D", content_base_link=content_base_link, user=user
            )
            return Response(status=status.HTTP_204_NO_CONTENT)


class InlineContentBaseLinkViewset(ModelViewSet):
    serializer_class = ContentBaseLinkSerializer
    lookup_url_kwarg = "contentbaselink_uuid"
    permission_classes = [IsAuthenticated, ProjectPermission]

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContentBaseLink.objects.none()  # pragma: no cover
        use_case = intelligences.ListContentBaseLinkUseCase()
        project_uuid = self.kwargs.get("project_uuid")
        return use_case.get_inline_contentbase_link(project_uuid=project_uuid)

    def create(self, request, **kwargs):
        content_base = intelligences.get_default_content_base_by_project(self.kwargs.get("project_uuid"))
        if not content_base:
            return Response(
                data={"message": "No content base found for this project"}, status=status.HTTP_404_NOT_FOUND
            )

        content_base_uuid = str(content_base.uuid)

        user: User = request.user
        user_email: str = user.email

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        link = serializer.validated_data.get("link")
        link_dto = intelligences.ContentBaseLinkDTO(
            link=link, user_email=user_email, content_base_uuid=content_base_uuid
        )
        content_base_link = intelligences.CreateContentBaseLinkUseCase().create_content_base_link(link_dto)

        try:
            project = ProjectsUseCase().get_by_uuid(self.kwargs.get("project_uuid"))
            indexer_database = project.indexer_database
        except ObjectDoesNotExist:
            indexer_database = Project.SENTENX

        if indexer_database == Project.BEDROCK:
            bedrock_send_link.delay(
                link=link, user_email=user_email, content_base_link_uuid=str(content_base_link.uuid)
            )
        else:
            send_link.delay(link=link, user_email=user_email, content_base_link_uuid=str(content_base_link.uuid))

        response = CreatedContentBaseLinkSerializer(content_base_link).data

        return Response(response, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        contentbaselink_uuid: str = kwargs.get("contentbaselink_uuid")
        use_case = intelligences.RetrieveContentBaseLinkUseCase()
        content_base_link = use_case.get_inline_contentbaselink(contentbaselink_uuid=contentbaselink_uuid)
        serializer = self.get_serializer(content_base_link)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        try:
            contentbaselink_uuid: str = kwargs.get("contentbaselink_uuid")

            content_base = intelligences.get_default_content_base_by_project(self.kwargs.get("project_uuid"))
            if not content_base:
                return Response(
                    data={"message": "No content base found for this project"}, status=status.HTTP_404_NOT_FOUND
                )

            content_base_uuid = str(content_base.uuid)

            use_case = intelligences.RetrieveContentBaseLinkUseCase()
            content_base_link = use_case.get_inline_contentbaselink(contentbaselink_uuid=contentbaselink_uuid)
            project_use_case = ProjectsUseCase()
            project = project_use_case.get_project_by_content_base_uuid(content_base_uuid)
            indexer = project_use_case.get_indexer_database_by_project(project)

            use_case = intelligences.DeleteContentBaseLinkUseCase(indexer)
            use_case.delete_by_object(
                content_base_link,
            )

            if project.indexer_database == Project.BEDROCK:
                start_ingestion_job.delay("", post_delete=True, project_uuid=str(project.uuid))

            event_manager.notify(
                event="contentbase_link_activity",
                action_type="D",
                content_base_link=content_base_link,
                user=self.request.user,
            )

            return Response(status=status.HTTP_204_NO_CONTENT)
        except ObjectDoesNotExist:
            indexer = SentenXFileDataBase
            use_case = intelligences.DeleteContentBaseLinkUseCase(indexer)
            use_case.delete_by_object(
                content_base_link,
            )
            event_manager.notify(
                event="contentbase_link_activity",
                action_type="D",
                content_base_link=content_base_link,
                user=self.request.user,
            )
            return Response(status=status.HTTP_204_NO_CONTENT)


class DownloadFileViewSet(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            file_name = request.data.get("file_name")
            contentbasefile_uuid = request.data.get("content_base_file")
            user_email = request.user.email

            use_case = intelligences.RetrieveContentBaseFileUseCase()
            content_base_file = use_case.get_contentbasefile(
                contentbasefile_uuid=contentbasefile_uuid, user_email=user_email
            )
            content_base_uuid = str(content_base_file.content_base.uuid)
            try:
                project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
                indexer_database = project.indexer_database
            except ObjectDoesNotExist:
                indexer_database = Project.SENTENX

            if indexer_database == Project.BEDROCK:
                file_name = f"{content_base_uuid}/{file_name}"
                file = BedrockFileDatabase().create_presigned_url(file_name)
            else:
                file = s3FileDatabase().create_presigned_url(file_name)

            return Response(data={"file": file}, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


class LogsViewSet(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, content_base_uuid, log_uuid):
        try:
            user = request.user
            org = get_org_by_content_base_uuid(content_base_uuid)

            has_permission = permissions.can_list_content_bases(user, org)
            if has_permission:
                feedback: int | None = request.data.get("feedback")

                if request.data.get("value") == "liked":
                    correct_answer = True
                else:
                    correct_answer = False

                log = intelligences.get_log_by_question_uuid(log_uuid)
                log.update_user_feedback(correct_answer, feedback)

                return Response(
                    data={
                        "question": log.question,
                        "feedback": log.feedback,
                        "value": "liked" if log.correct_answer else "disliked",
                    },
                    status=200,
                )
            raise IntelligencePermissionDenied()
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


class RouterContentBaseViewSet(views.APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid):
        content_base = intelligences.get_by_uuid.get_default_content_base_by_project(project_uuid)
        return Response(data=RouterContentBaseSerializer(content_base).data, status=200)


class RouterRetailViewSet(views.APIView):
    def _create_links(self, links: list, user: User, content_base: ContentBase, project: Project) -> list:
        created_links = []
        if links:
            for link in links:
                link_serializer = ContentBaseLinkSerializer(data={"link": link})
                link_serializer.is_valid(raise_exception=True)
                link_dto = intelligences.ContentBaseLinkDTO(
                    link=link, user_email=user.email, content_base_uuid=str(content_base.uuid)
                )
                content_base_link = intelligences.CreateContentBaseLinkUseCase().create_content_base_link(link_dto)

                if project.indexer_database == Project.BEDROCK:
                    bedrock_send_link.delay(
                        link=link, user_email=user.email, content_base_link_uuid=str(content_base_link.uuid)
                    )
                else:
                    send_link.delay(
                        link=link, user_email=user.email, content_base_link_uuid=str(content_base_link.uuid)
                    )

                link_serializer = CreatedContentBaseLinkSerializer(content_base_link).data
                created_links.append(link_serializer)

    # TODO - Refactor this view to have only one searializer and no dependencies
    def post(self, request, project_uuid):
        user: User = request.user
        module_permission = user.has_perm("users.can_communicate_internally")

        if not module_permission:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        use_case = intelligences.RetrieveContentBaseUseCase()
        content_base = use_case.get_default_by_project(project_uuid, user.email, is_superuser=module_permission)
        links: list = request.data.get("links")

        project = ProjectsUseCase().get_project_by_content_base_uuid(content_base.uuid)

        created_links = self._create_links(links, user, content_base, project)

        # ContentBasePersonalization

        agent_data = request.data.get("agent")

        instructions_objects = []
        if not content_base.instructions.exists():
            default_instructions: list = settings.DEFAULT_RETAIL_INSTRUCTIONS
            for instruction in default_instructions:
                instructions_objects.append(
                    {
                        "instruction": instruction,
                    }
                )

        agent = {"agent": agent_data, "instructions": instructions_objects}
        request.data["instructions"] = instructions_objects

        new_request = request._request
        new_request.data = request.data

        personalization_serializer = ContentBasePersonalizationSerializer(
            content_base, data=agent, partial=True, context={"request": new_request}
        )

        if personalization_serializer.is_valid():
            personalization_serializer.save()

        project.inline_agent_switch = True
        project.save()

        response = {"personalization": personalization_serializer.data, "links": created_links}

        return Response(response, status=200)

    def delete(self, request, project_uuid):
        user: User = request.user
        module_permission = user.has_perm("users.can_communicate_internally")

        if not module_permission:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        use_case = intelligences.RetrieveContentBaseUseCase()
        content_base = use_case.get_default_by_project(project_uuid, user.email, is_superuser=module_permission)
        content_base_uuid: str = content_base.uuid

        use_case = intelligences.RetrieveContentBaseLinkUseCase()
        existing_links = use_case.get_content_base_link_by_link(
            content_base_uuid=content_base_uuid, link=request.data.get("link")
        )

        for link in existing_links:
            project_use_case = ProjectsUseCase()
            project = project_use_case.get_project_by_content_base_uuid(content_base_uuid)
            indexer = project_use_case.get_indexer_database_by_project(project)

            use_case = intelligences.DeleteContentBaseLinkUseCase(indexer)
            use_case.delete_by_object(
                link,
            )

            if project.indexer_database == Project.BEDROCK:
                start_ingestion_job.delay("", post_delete=True, project_uuid=str(project.uuid))

            event_manager.notify(event="contentbase_link_activity", action_type="D", content_base_link=link, user=user)

        return Response(status=status.HTTP_204_NO_CONTENT)


class LLMViewset(views.APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid):
        llm_config = intelligences.get_llm_config(project_uuid=project_uuid)
        return Response(data=LLMConfigSerializer(llm_config).data, status=200)

    def patch(self, request, project_uuid):
        user_email = request.user.email
        llm_update_dto = intelligences.UpdateLLMDTO(
            user_email=user_email,
            project_uuid=project_uuid,
            model=request.data.get("model"),
            setup=request.data.get("setup"),
            advanced_options=request.data.get("advanced_options"),
        )
        usecase = intelligences.UpdateLLMUseCase()
        updated_llm = usecase.update_llm_by_project(llm_update_dto)

        return Response(data=LLMConfigSerializer(updated_llm).data, status=200)


class LLMDefaultViewset(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        user_email = request.user.email
        llm_update_dto = dict(
            user_email=user_email,
            project_uuid=project_uuid,
            model="WeniGPT",
            setup={
                "version": settings.WENIGPT_DEFAULT_VERSION,
                "top_k": settings.WENIGPT_TOP_K,
                "top_p": settings.WENIGPT_TOP_P,
                "max_length": settings.WENIGPT_MAX_LENGHT,
                "temperature": settings.WENIGPT_TEMPERATURE,
            },
            advanced_options={},
        )

        return Response(data=llm_update_dto, status=200)

    def post(self, request, project_uuid):
        user_email = request.user.email
        llm_update_dto = intelligences.UpdateLLMDTO(
            user_email=user_email,
            project_uuid=project_uuid,
            model="WeniGPT",
            setup={
                "version": settings.WENIGPT_DEFAULT_VERSION,
                "top_k": settings.WENIGPT_TOP_K,
                "top_p": settings.WENIGPT_TOP_P,
                "max_length": settings.WENIGPT_MAX_LENGHT,
                "temperature": settings.WENIGPT_TEMPERATURE,
            },
            advanced_options={},
        )
        usecase = intelligences.UpdateLLMUseCase()
        updated_llm = usecase.update_llm_by_project(llm_update_dto)

        return Response(data=LLMConfigSerializer(updated_llm).data, status=200)


class ContentBasePersonalizationViewSet(ModelViewSet):
    serializer_class = ContentBasePersonalizationSerializer
    authentication_classes = AUTHENTICATION_CLASSES

    def get_queryset(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            return ContentBase.objects.none()  # pragma: no cover
        super().get_serializer(*args, **kwargs)

    def list(self, request, *args, **kwargs):
        try:
            user_email = ""
            authorization_header = request.headers.get("Authorization", "Bearer unauthorized")
            is_super_user = permissions.is_super_user(authorization_header)

            if not is_super_user:
                user_email = request.user.email

            project_uuid = kwargs.get("project_uuid")

            content_base = intelligences.RetrieveContentBaseUseCase().get_default_by_project(
                project_uuid, user_email, is_super_user
            )
            data = ContentBasePersonalizationSerializer(
                content_base, context={"request": request, "project_uuid": project_uuid}
            ).data
            return Response(data=data, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def update(self, request, *args, **kwargs):
        try:
            project_uuid = kwargs.get("project_uuid")
            content_base = intelligences.RetrieveContentBaseUseCase().get_default_by_project(
                project_uuid, request.user.email
            )

            context = {"request": request, "project_uuid": project_uuid}

            if "team_data" in request.data:
                request.data["team"] = request.data.pop("team_data")

            serializer = ContentBasePersonalizationSerializer(
                content_base, data=request.data, partial=True, context=context
            )

            if serializer.is_valid():
                serializer.save()
                data = serializer.data
                return Response(data=data, status=status.HTTP_200_OK)
            else:
                import logging

                logger = logging.getLogger(__name__)
                logger.error("Serializer errors", extra={"errors": serializer.errors})
                return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error("Error updating personalization: %s", str(e), exc_info=True)
            return Response(data={"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def destroy(self, request, *args, **kwargs):
        try:
            instruction_id = request.query_params.get("id")
            project_uuid = kwargs.get("project_uuid")
            content_base = intelligences.RetrieveContentBaseUseCase().get_default_by_project(
                project_uuid, request.user.email
            )
            user = request.user

            ids = [instruction_id]
            intelligences.DeleteContentBaseUseCase().bulk_delete_instruction_by_id(content_base, ids, user)
            data = ContentBasePersonalizationSerializer(content_base, context={"request": request}).data
            return Response(status=status.HTTP_200_OK, data=data)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


class ContentBaseFilePreview(views.APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def post(self, request, *args, **kwargs):
        try:
            project_uuid = kwargs.get("project_uuid")
            content_base = request.data.get("content_base_uuid")
            content_base_file_uuid = request.data.get("content_base_file_uuid")
            page_size = request.data.get("page_size", 10000)
            page_number = request.data.get("page_number", 1)

            project = get_project_by_uuid(project_uuid)
            search_file_database = SentenXDocumentPreview()

            cb_org = get_org_by_content_base_uuid(content_base)
            project_org = project.org
            if not cb_org == project_org:
                raise IntelligencePermissionDenied()

            response = search_file_database.document_preview(
                content_base_file_uuid=content_base_file_uuid,
                content_base_uuid=content_base,
                page_size=page_size,
                page_number=page_number,
            )
            return Response(data=response, status=200)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return Response(data={"message": str(e)}, status=500)


class UploadFileView(views.APIView):
    permission_classes = [ProjectPermission]

    def post(self, request, *args, **kwargs):
        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

        if not validate_mime_type(file.content_type):
            return Response({"error": f"invalid file type: {file.content_type}"}, status=status.HTTP_400_BAD_REQUEST)

        storage = AttachmentPreviewStorage(
            bucket_name=settings.AWS_S3_BUCKET_NAME,
        )
        file_name = storage.save(file.name, file)
        file_name = f"media/preview/attachments/{file_name}"
        file_url = s3FileDatabase().create_presigned_url(file_name)

        delete_file_task.apply_async((file_name,), countdown=600)

        return Response({"file_url": file_url}, status=status.HTTP_201_CREATED)


class CommerceHasAgentBuilder(views.APIView):
    def get(eslf, request):
        user: User = request.user
        module_permission = user.has_perm("users.can_communicate_internally")

        if not module_permission:
            return Response({"error": "you dont have permission"}, status=status.HTTP_401_UNAUTHORIZED)

        project_uuid = request.query_params.get("project_uuid", None)

        if not project_uuid:
            return Response({"Error": "The project_uuid is required!"}, status=status.HTTP_400_BAD_REQUEST)

        content_base = get_default_content_base_by_project(project_uuid=project_uuid)
        agent = content_base.agent
        if agent is None:
            return Response(
                {
                    "message": "The agent isn't configured!",
                    "data": {
                        "has_agent": False,
                    },
                },
                status=status.HTTP_200_OK,
            )
        if agent.name:
            links = []
            for content_base_link in content_base.contentbaselinks.all():
                links.append(content_base_link.link)
            return Response(
                {
                    "message": "The agent is configured!",
                    "data": {
                        "has_agent": True,
                        "name": agent.name,
                        "objective": agent.goal,
                        "occupation": agent.role,
                        "links": links,
                    },
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {
                    "message": "The agent isn't configured!",
                    "data": {
                        "has_agent": False,
                    },
                },
                status=status.HTTP_200_OK,
            )


class TopicsViewSet(ModelViewSet):
    serializer_class = TopicsSerializer
    permission_classes = [CombinedExternalProjectPermission]
    authentication_classes = []  # Disable default authentication
    lookup_field = "uuid"

    def get_queryset(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            return Topics.objects.none()  # pragma: no cover

        project_uuid = self.kwargs.get("project_uuid")
        if project_uuid:
            return Topics.objects.filter(project__uuid=project_uuid)
        return Topics.objects.none()

    def create(self, request, *args, **kwargs):
        project_uuid = self.kwargs.get("project_uuid")
        if not project_uuid:
            return Response({"error": "project_uuid is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(project=project)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SubTopicsViewSet(ModelViewSet):
    serializer_class = SubTopicsSerializer
    permission_classes = [CombinedExternalProjectPermission]
    authentication_classes = []  # Disable default authentication
    lookup_field = "uuid"

    def get_queryset(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            return SubTopics.objects.none()  # pragma: no cover

        topic_uuid = self.kwargs.get("topic_uuid")
        if topic_uuid:
            return SubTopics.objects.filter(topic__uuid=topic_uuid)
        return SubTopics.objects.none()

    def create(self, request, *args, **kwargs):
        topic_uuid = self.kwargs.get("topic_uuid")
        if not topic_uuid:
            return Response({"error": "topic_uuid is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            topic = Topics.objects.get(uuid=topic_uuid)
        except Topics.DoesNotExist:
            return Response({"error": "Topic not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(topic=topic)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SupervisorViewset(ModelViewSet):
    serializer_class = SupervisorDataSerializer
    permission_classes = [ProjectPermission]
    pagination_class = SupervisorPagination
    lookup_field = "uuid"
    filter_backends = [filters.DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ConversationFilter
    search_fields = ["contact_name", "contact_urn"]
    ordering_fields = ["created_at", "start_date", "end_date"]
    ordering = ["-start_date"]

    def get_filter_backends(self):
        """Disable filter backends during schema generation to avoid duplicate parameters"""
        if getattr(self, "swagger_fake_view", False):
            return []  # Return empty list to prevent filter backend from adding parameters
        return [filters.DjangoFilterBackend, SearchFilter, OrderingFilter]

    def get_queryset(self):
        # Prevent database access during schema generation
        if getattr(self, "swagger_fake_view", False):
            return Conversation.objects.none()

        project_uuid = self.kwargs.get("project_uuid")
        if not project_uuid:
            return Conversation.objects.none()

        try:
            project = get_project_by_uuid(project_uuid)
            return Conversation.objects.select_related("topic", "project").filter(project=project)
        except ProjectDoesNotExist:
            return Conversation.objects.none()

    @extend_schema(
        operation_id="supervisor_list",
        summary="List supervisor conversation data",
        description=(
            "Returns paginated supervisor conversation data for a project.\n\n"
            "Filters: start_date (DD-MM-YYYY), end_date (DD-MM-YYYY), csat, resolution, topics, "
            "has_chats_room, nps, search. Supports ordering and search."
        ),
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.PATH,
                description="Project UUID",
                required=True,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="start_date", description="Start date (DD-MM-YYYY)", required=False, type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name="end_date", description="End date (DD-MM-YYYY)", required=False, type=OpenApiTypes.STR
            ),
            OpenApiParameter(name="csat", description="CSAT filter", required=False, type=OpenApiTypes.NUMBER),
            OpenApiParameter(name="resolution", description="Resolution filter", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="topics", description="Topics filter", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(
                name="has_chats_room", description="Has human chat room", required=False, type=OpenApiTypes.BOOL
            ),
            OpenApiParameter(name="nps", description="NPS filter", required=False, type=OpenApiTypes.NUMBER),
            OpenApiParameter(
                name="search", description="Search by contact name or URN", required=False, type=OpenApiTypes.STR
            ),
        ],
        responses={
            200: OpenApiResponse(description="Lista paginada de conversas", response=SupervisorDataSerializer),
            400: OpenApiResponse(description="Invalid parameters"),
            404: OpenApiResponse(description="Project not found"),
            500: OpenApiResponse(description="Internal error"),
        },
        tags=["Supervisor"],
    )
    def list(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        if not project_uuid:
            return Response({"error": "project_uuid is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            queryset = self.filter_queryset(self.get_queryset())

            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except ProjectDoesNotExist:
            return Response({"error": f"Project with UUID {project_uuid} not found"}, status=status.HTTP_404_NOT_FOUND)
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid date format. Expected DD-MM-YYYY format"}, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            error_str = str(e)
            if "not a valid UUID" in error_str:
                return Response(
                    {"error": f"Project with UUID {project_uuid} not found"}, status=status.HTTP_404_NOT_FOUND
                )
            elif "Enter a valid date" in error_str:
                return Response(
                    {"error": "Invalid date format. Expected DD-MM-YYYY format"}, status=status.HTTP_400_BAD_REQUEST
                )

            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.capture_exception(e)

            import logging

            logger = logging.getLogger(__name__)
            logger.error("Error retrieving supervisor data: %s", str(e), exc_info=True)
            return Response(
                {"error": f"Error retrieving supervisor data: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class InstructionsClassificationAPIView(APIView):
    authentication_classes = AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated, ProjectPermission]

    @extend_schema(
        operation_id="instruction_classify",
        summary="Classify instruction",
        description=(
            "Classifies an instruction based on the project's existing content base instructions. "
            "Returns suggested categories and an improvement suggestion."
        ),
        request=InstructionClassificationRequestSerializer,
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.PATH,
                description="Project UUID",
                required=True,
                type=OpenApiTypes.STR,
            )
        ],
        responses={
            200: OpenApiResponse(
                description="Classification done", response=InstructionClassificationResponseSerializer
            ),
            400: OpenApiResponse(description="Bad request"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden"),
            500: OpenApiResponse(description="Internal error"),
        },
        tags=["Instructions"],
    )
    def post(self, request, project_uuid):
        try:
            serializer = InstructionClassificationRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            instruction = serializer.validated_data["instruction"]
            language = serializer.validated_data["language"]

            user = request.user
            name = user.name or user.email.split("@")[0]
            occupation = getattr(user, "occupation", "Customer Service Agent")

            from nexus.usecases.intelligences.get_by_uuid import get_project_and_content_base_data

            project, content_base, _ = get_project_and_content_base_data(project_uuid)

            goal = content_base.agent.goal if content_base.agent else "Provide excellent customer support"
            adjective = content_base.agent.personality if content_base.agent else "friendly"

            instructions = []
            for instruction_obj in content_base.instructions.all():
                instructions.append({"instruction": instruction_obj.instruction, "type": "custom"})

            from nexus.usecases.intelligences.lambda_usecase import LambdaUseCase

            lambda_usecase = LambdaUseCase()

            classification, suggestion = lambda_usecase.instruction_classify(
                name=name,
                occupation=occupation,
                goal=goal,
                adjective=adjective,
                instructions=instructions,
                instruction_to_classify=instruction,
                language=language,
            )

            return Response({"classification": classification, "suggestion": suggestion}, status=status.HTTP_200_OK)

        except Exception as e:
            sentry_sdk.capture_exception(e)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
