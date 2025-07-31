import os
import pendulum
import sentry_sdk
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils.datastructures import MultiValueDictKeyError
from rest_framework import parsers, status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from nexus.authentication import AUTHENTICATION_CLASSES
from nexus.events import event_manager
from nexus.intelligences.models import (
    ContentBase,
    ContentBaseFile,
    ContentBaseText,
    Intelligence,
    Topics,
    SubTopics,
    Conversation,
)
from nexus.orgs import permissions
from nexus.paginations import CustomCursorPagination, SupervisorPagination
from nexus.projects.models import Project
from nexus.projects.api.permissions import ProjectPermission, CombinedExternalProjectPermission
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
    IntelligencePermissionDenied,
)
from nexus.usecases.intelligences.get_by_uuid import (
    get_default_content_base_by_project,
)
from nexus.usecases.intelligences.supervisor import Supervisor
from nexus.usecases.orgs.get_by_uuid import get_org_by_content_base_uuid
from nexus.usecases.projects.get_by_uuid import get_project_by_uuid
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from nexus.projects.exceptions import ProjectDoesNotExist
from nexus.usecases.task_managers.celery_task_manager import (
    CeleryTaskManagerUseCase,
)
from nexus.usecases.task_managers.file_database import (
    get_gpt_by_content_base_uuid,
)
from nexus.users.models import User

from .serializers import (
    ContentBaseFileSerializer,
    ContentBaseLinkSerializer,
    ContentBasePersonalizationSerializer,
    ContentBaseSerializer,
    ContentBaseTextSerializer,
    CreatedContentBaseLinkSerializer,
    IntelligenceSerializer,
    LLMConfigSerializer,
    RouterContentBaseSerializer,
    TopicsSerializer,
    SubTopicsSerializer,
    SupervisorDataSerializer,
)


class IntelligencesViewset(
    ModelViewSet
):

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
        org_uuid = self.kwargs.get('org_uuid')
        use_case_list = use_case.get_org_intelligences(
            org_uuid,
            user_email=user_email
        )

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
            intelligence_uuid = kwargs.get('pk')
            use_case = intelligences.RetrieveIntelligenceUseCase()
            intelligence = use_case.get_intelligence(
                intelligence_uuid=intelligence_uuid,
                user_email=user_email
            )
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

            name = serializer.validated_data.get('name')
            description = serializer.validated_data.get('description')

            intelligence = use_case.create_intelligences(
                org_uuid=org_uuid,
                name=name,
                description=description,
                user_email=user_email
            )

            return Response(
                IntelligenceSerializer(intelligence).data,
                status=status.HTTP_201_CREATED
            )
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def update(self, request, *args, **kwargs):
        self.validate_kwargs(kwargs)
        try:
            user_email = request.user.email
            use_case = intelligences.UpdateIntelligenceUseCase()

            update_intelligence = use_case.update_intelligences(
                intelligence_uuid=kwargs.get("pk"),
                name=request.data.get('name'),
                description=request.data.get('description'),
                user_email=user_email
            )

            return Response(
                IntelligenceSerializer(update_intelligence).data,
                status=status.HTTP_200_OK
            )
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def destroy(self, request, **kwargs):
        self.validate_kwargs(kwargs)
        try:
            user_email = request.user.email
            use_case = intelligences.DeleteIntelligenceUseCase()

            intelligence_uuid = kwargs.get('pk')

            use_case.delete_intelligences(
                intelligence_uuid=intelligence_uuid,
                user_email=user_email
            )

            return Response(
                status=status.HTTP_204_NO_CONTENT
            )
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


class FlowsIntelligencesApiView(views.APIView):
    authentication_classes = []

    def get(self, request, project_uuid):
        authorization_header = request.headers.get('Authorization', "Bearer unauthorized")

        is_super_user = permissions.is_super_user(authorization_header)

        if not is_super_user:
            raise PermissionDenied('You do not have permission to perform this action.')

        list_use_case = intelligences.ListAllIntelligenceContentUseCase()
        return Response(data=list_use_case.get_project_intelligences(project_uuid=project_uuid, is_super_user=is_super_user), status=200)


class GenerativeIntelligenceQuestionAPIView(views.APIView):
    authentication_classes = []

    def post(self, request):
        authorization_header = request.headers.get("Authorization", "Bearer unauthorized")

        if not permissions.is_super_user(authorization_header):
            raise PermissionDenied('You do not have permission to perform this action.')

        data = request.data

        custom_rules_content_base_uuid = os.environ.get("CUSTOM_RULES_CONTENT_BASE_UUID")

        content_base_uuid = data.get("content_base_uuid")
        generative_ai_database = get_gpt_by_content_base_uuid(content_base_uuid)

        db = SentenXFileDataBase() if content_base_uuid != custom_rules_content_base_uuid else BedrockFileDatabase()

        intelligence_usecase = intelligences.IntelligenceGenerativeSearchUseCase(
            search_file_database=db,
            generative_ai_database=generative_ai_database
        )
        data = intelligence_usecase.search(content_base_uuid=content_base_uuid, text=data.get("text"), language=data.get("language"))
        if data.get("answers"):
            return Response(
                data=data,
                status=200
            )
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
                        language=data.get("language", "pt-br")
                    ),
                    status=200
                )
            raise IntelligencePermissionDenied()
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


class SentenxIndexerUpdateFile(views.APIView):
    authentication_classes = []

    def patch(self, request):
        authorization_header = request.headers.get('Authorization', "Bearer unauthorized")
        if not permissions.is_super_user(authorization_header):
            raise PermissionDenied("You has not permission to do that.")
        data = request.data
        task_manager_usecase = CeleryTaskManagerUseCase()
        sentenx_status = [ContentBaseFileTaskManager.STATUS_FAIL, ContentBaseFileTaskManager.STATUS_SUCCESS]
        task_manager_usecase.update_task_status(task_uuid=data.get("task_uuid"), status=sentenx_status[data.get("status")], file_type=data.get("file_type"))
        return Response(status=200, data=data)


class ContentBaseViewset(
    ModelViewSet
):

    pagination_class = CustomCursorPagination
    serializer_class = ContentBaseSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "contentbase_uuid"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContentBase.objects.none()  # pragma: no cover
        user_email = self.request.user.email
        use_case = intelligences.ListContentBaseUseCase()
        intelligence_uuid = self.kwargs.get('intelligence_uuid')
        use_case_list = use_case.get_intelligence_contentbases(
            intelligence_uuid,
            user_email=user_email
        )
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
                contentbase_uuid=kwargs.get('contentbase_uuid'),
                user_email=user_email
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

            title = serializer.validated_data.get('title')
            description = serializer.validated_data.get('description')
            language = serializer.validated_data.get('language')

            contentbase = use_case.create_contentbase(
                intelligence_uuid=intelligence_uuid,
                title=title,
                user_email=user_email,
                description=description,
                language=language
            )

            return Response(
                ContentBaseSerializer(contentbase).data,
                status=status.HTTP_201_CREATED
            )
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def update(self, request, intelligence_uuid: str, **kwargs):
        try:
            user_email = request.user.email
            use_case = intelligences.UpdateContentBaseUseCase()

            update_contentbase = use_case.update_contentbase(
                contentbase_uuid=kwargs.get('contentbase_uuid'),
                title=request.data.get('title'),
                language=request.data.get('language'),
                description=request.data.get('description'),
                user_email=user_email
            )

            return Response(
                ContentBaseSerializer(update_contentbase).data,
                status=status.HTTP_200_OK
            )
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def destroy(self, request, intelligence_uuid: str, **kwargs):
        try:
            user_email = request.user.email
            use_case = intelligences.DeleteContentBaseUseCase()

            contentbase_uuid = kwargs.get('contentbase_uuid')

            use_case.delete_contentbase(
                contentbase_uuid=contentbase_uuid,
                user_email=user_email
            )

            return Response(
                status=status.HTTP_204_NO_CONTENT
            )
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


class ContentBaseTextViewset(
    ModelViewSet
):

    pagination_class = CustomCursorPagination
    serializer_class = ContentBaseTextSerializer
    lookup_url_kwarg = "contentbasetext_uuid"
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContentBaseText.objects.none()  # pragma: no cover
        user_email = self.request.user.email
        use_case = intelligences.ListContentBaseTextUseCase()
        contentbase_uuid = self.kwargs.get('content_base_uuid')
        use_case_list = use_case.get_contentbase_contentbasetexts(
            contentbase_uuid,
            user_email=user_email
        )
        return use_case_list

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def retrieve(self, request, *args, **kwargs):
        try:
            user_email = request.user.email
            contentbasetext_uuid = kwargs.get('contentbasetext_uuid')

            use_case = intelligences.RetrieveContentBaseTextUseCase()
            contentbasetext = use_case.get_contentbasetext(
                contentbasetext_uuid=contentbasetext_uuid,
                user_email=user_email
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

            text = serializer.validated_data.get('text')
            content_base = intelligences.get_by_contentbase_uuid(content_base_uuid)
            cb_dto = intelligences.ContentBaseDTO(
                uuid=content_base.uuid,
                title=content_base.title,
                intelligence_uuid=content_base.intelligence.uuid,
                created_by_email=content_base.created_by.email,
            )
            cbt_dto = intelligences.ContentBaseTextDTO(
                text=text,
                content_base_uuid=content_base_uuid,
                user_email=user_email
            )
            content_base_text = intelligences.CreateContentBaseTextUseCase().create_contentbasetext(
                content_base_dto=cb_dto,
                content_base_text_dto=cbt_dto
            )
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
            if project.indexer_database == Project.BEDROCK:
                bedrock_upload_text_file.delay(
                    content_base_dto=cb_dto.__dict__,
                    content_base_text_uuid=str(content_base_text.uuid),
                    text=text
                )

            else:
                upload_text_file.delay(
                    content_base_dto=cb_dto.__dict__,
                    content_base_text_uuid=content_base_text.uuid,
                    text=text
                )

            response = ContentBaseTextSerializer(content_base_text).data

            return Response(
                response,
                status=status.HTTP_201_CREATED
            )
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except ObjectDoesNotExist:
            upload_text_file.delay(
                content_base_dto=cb_dto.__dict__,
                content_base_text_uuid=content_base_text.uuid,
                text=text
            )
            response = ContentBaseTextSerializer(content_base_text).data

            return Response(
                response,
                status=status.HTTP_201_CREATED
            )

    def update(self, request, **kwargs):
        try:
            user_email = request.user.email
            text = request.data.get('text')
            content_base_uuid = kwargs.get('content_base_uuid')
            content_base_text_uuid = kwargs.get('contentbasetext_uuid')
            content_base = intelligences.get_by_contentbase_uuid(content_base_uuid)
            content_base_text = intelligences.get_by_contentbasetext_uuid(content_base_text_uuid)
            cb_dto = intelligences.ContentBaseDTO(
                uuid=content_base.uuid,
                title=content_base.title,
                intelligence_uuid=content_base.intelligence.uuid,
                created_by_email=content_base.created_by.email,
            )
            content_base_text = intelligences.UpdateContentBaseTextUseCase().update_contentbasetext(
                contentbasetext=content_base_text,
                user_email=user_email,
                text=text
            )
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
            file_database = ProjectsUseCase().get_indexer_database_by_project(project)

            delete_use_case = intelligences.DeleteContentBaseTextUseCase(file_database())
            delete_use_case.delete_content_base_text_from_index(
                content_base_text_uuid,
                content_base_uuid,
                content_base_text.file_name
            )

            if project.indexer_database == Project.BEDROCK:
                bedrock_upload_text_file.delay(
                    content_base_dto=cb_dto.__dict__,
                    content_base_text_uuid=str(content_base_text.uuid),
                    text=text
                )
            else:
                upload_text_file.delay(
                    content_base_dto=cb_dto.__dict__,
                    content_base_text_uuid=content_base_text.uuid,
                    text=text,
                )

            response = ContentBaseTextSerializer(content_base_text).data

            return Response(
                response,
                status=status.HTTP_200_OK
            )
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except ObjectDoesNotExist:
            file_database = SentenXFileDataBase
            delete_use_case = intelligences.DeleteContentBaseTextUseCase(file_database())
            delete_use_case.delete_content_base_text_from_index(
                content_base_text_uuid,
                content_base_uuid,
                content_base_text.file_name
            )
            upload_text_file.delay(
                content_base_dto=cb_dto.__dict__,
                content_base_text_uuid=content_base_text.uuid,
                text=text,
            )
            response = ContentBaseTextSerializer(content_base_text).data
            return Response(
                response,
                status=status.HTTP_200_OK
            )

    def destroy(self, request, **kwargs):
        try:
            user_email = request.user.email
            content_base_uuid = kwargs.get("content_base_uuid")
            project_use_case = ProjectsUseCase()
            project = project_use_case.get_project_by_content_base_uuid(content_base_uuid)
            indexer = project_use_case.get_indexer_database_by_project(project)
            use_case = intelligences.DeleteContentBaseTextUseCase(indexer())

            contentbasetext_uuid = kwargs.get('contentbasetext_uuid')
            use_case.delete_contentbasetext(
                contentbasetext_uuid=contentbasetext_uuid,
                user_email=user_email
            )

            return Response(
                status=status.HTTP_204_NO_CONTENT
            )
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except ObjectDoesNotExist:
            indexer = SentenXFileDataBase
            use_case = intelligences.DeleteContentBaseTextUseCase(indexer())

            contentbasetext_uuid = kwargs.get('contentbasetext_uuid')
            use_case.delete_contentbasetext(
                contentbasetext_uuid=contentbasetext_uuid,
                user_email=user_email
            )
            return Response(
                status=status.HTTP_204_NO_CONTENT
            )


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

    def create(self, request, content_base_uuid=str):
        from rest_framework import status as http_status

        def validate_file_size(file):
            # default 50 MiB
            if file.size > (settings.BEDROCK_FILE_SIZE_LIMIT * (1024**2)):
                return Response(data={"message": "File size is too large"}, status=http_status.HTTP_400_BAD_REQUEST)

        try:
            self.get_queryset()

            user: User = request.user
            file: InMemoryUploadedFile = request.FILES['file']
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
                file,
                content_base_uuid,
                extension_file,
                user_email,
                load_type,
                filename=file.name
            )

            return Response(
                response,
                status=http_status.HTTP_201_CREATED
            )

        except MultiValueDictKeyError:
            return Response(data={"message": "file is required"}, status=http_status.HTTP_400_BAD_REQUEST)
        except IntelligencePermissionDenied:
            return Response(status=http_status.HTTP_401_UNAUTHORIZED)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContentBaseFile.objects.none()  # pragma: no cover
        use_case = intelligences.ListContentBaseFileUseCase()
        contentbase_uuid = self.kwargs.get('content_base_uuid')
        return use_case.get_contentbase_file(contentbase_uuid=contentbase_uuid, user_email=self.request.user.email)

    def retrieve(self, request, *args, **kwargs):
        try:
            user_email: str = self.request.user.email
            contentbasefile_uuid: str = kwargs.get('contentbase_file_uuid')
            use_case = intelligences.RetrieveContentBaseFileUseCase()
            contentbasetext = use_case.get_contentbasefile(
                contentbasefile_uuid=contentbasefile_uuid,
                user_email=user_email
            )
            serializer = self.get_serializer(contentbasetext)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def destroy(self, request, *args, **kwargs):
        try:
            user_email: str = self.request.user.email
            contentbasefile_uuid: str = kwargs.get('contentbase_file_uuid')
            content_base_uuid: str = kwargs.get('content_base_uuid')
            use_case = intelligences.RetrieveContentBaseFileUseCase()
            content_base_file = use_case.get_contentbasefile(
                contentbasefile_uuid=contentbasefile_uuid,
                user_email=user_email
            )
            project_use_case = ProjectsUseCase()
            project = project_use_case.get_project_by_content_base_uuid(content_base_uuid)
            indexer = project_use_case.get_indexer_database_by_project(project)
            intelligences.DeleteContentBaseFileUseCase(indexer).delete_by_object(content_base_file)

            if project.indexer_database == Project.BEDROCK:
                start_ingestion_job.delay("", post_delete=True)

            event_manager.notify(
                event="contentbase_file_activity",
                action_type="D",
                content_base_file=content_base_file,
                user=self.request.user
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ObjectDoesNotExist:
            indexer = SentenXFileDataBase
            intelligences.DeleteContentBaseFileUseCase(indexer).delete_by_object(content_base_file)
            event_manager.notify(
                event="contentbase_file_activity",
                action_type="D",
                content_base_file=content_base_file,
                user=self.request.user
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

        print("STARTING INLINE CONTENT BASE FILE CREATE")

        def validate_file_size(file):
            # default 50 MiB
            if file.size > (settings.BEDROCK_FILE_SIZE_LIMIT * (1024**2)):
                return Response(data={"message": "File size is too large"}, status=http_status.HTTP_400_BAD_REQUEST)

        content_base = self.get_queryset()
        if not content_base:
            return Response(data={"message": "No content base found for this project"}, status=http_status.HTTP_404_NOT_FOUND)

        content_base_uuid = str(content_base.uuid)

        user: User = request.user
        file: InMemoryUploadedFile = request.FILES['file']
        validate_file_size(file)
        user_email: str = user.email
        extension_file: str = request.data.get("extension_file")
        load_type = request.data.get("load_type")

        file_manager = CeleryFileManager()

        try:
            project = ProjectsUseCase().get_by_uuid(self.kwargs.get('project_uuid'))
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
            file,
            content_base_uuid,
            extension_file,
            user_email,
            load_type,
            filename=file.name
        )

        return Response(
            response,
            status=http_status.HTTP_201_CREATED
        )

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContentBaseFile.objects.none()  # pragma: no cover
        project_uuid = self.kwargs.get('project_uuid')
        content_base = intelligences.get_by_uuid.get_default_content_base_by_project(project_uuid)
        return content_base

    def retrieve(self, request, *args, **kwargs):

        contentbasefile_uuid: str = kwargs.get('contentbase_file_uuid')
        use_case = intelligences.RetrieveContentBaseFileUseCase()
        contentbasetext = use_case.get_inline_contentbase_file(
            contentbasefile_uuid=contentbasefile_uuid
        )
        serializer = self.get_serializer(contentbasetext)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        try:
            contentbasefile_uuid: str = kwargs.get('contentbase_file_uuid')

            content_base = self.get_queryset()
            if not content_base:
                return Response(data={"message": "No content base found for this project"}, status=status.HTTP_404_NOT_FOUND)

            content_base_uuid = str(content_base.uuid)

            use_case = intelligences.RetrieveContentBaseFileUseCase()
            content_base_file = use_case.get_inline_contentbase_file(
                contentbasefile_uuid=contentbasefile_uuid
            )
            project_use_case = ProjectsUseCase()
            project = project_use_case.get_project_by_content_base_uuid(content_base_uuid)
            indexer = project_use_case.get_indexer_database_by_project(project)
            intelligences.DeleteContentBaseFileUseCase(indexer).delete_by_object(content_base_file)

            if project.indexer_database == Project.BEDROCK:
                start_ingestion_job.delay("", post_delete=True)

            event_manager.notify(
                event="contentbase_file_activity",
                action_type="D",
                content_base_file=content_base_file,
                user=self.request.user
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ObjectDoesNotExist:
            indexer = SentenXFileDataBase
            intelligences.DeleteContentBaseFileUseCase(indexer).delete_by_object(content_base_file)
            event_manager.notify(
                event="contentbase_file_activity",
                action_type="D",
                content_base_file=content_base_file,
                user=self.request.user
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
        contentbase_uuid = self.kwargs.get('content_base_uuid')
        return use_case.get_contentbase_link(contentbase_uuid=contentbase_uuid, user_email=self.request.user.email)

    def create(self, request, content_base_uuid: str):
        try:
            user_email = request.user.email
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            link = serializer.validated_data.get('link')
            content_base = intelligences.get_by_contentbase_uuid(content_base_uuid)
            link_dto = intelligences.ContentBaseLinkDTO(
                link=link,
                user_email=user_email,
                content_base_uuid=str(content_base.uuid)
            )
            content_base_link = intelligences.CreateContentBaseLinkUseCase().create_content_base_link(link_dto)
            project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)

            if project.indexer_database == Project.BEDROCK:
                bedrock_send_link.delay(
                    link=link,
                    user_email=user_email,
                    content_base_link_uuid=str(content_base_link.uuid)
                )
            else:
                send_link.delay(
                    link=link,
                    user_email=user_email,
                    content_base_link_uuid=str(content_base_link.uuid)
                )

            response = CreatedContentBaseLinkSerializer(content_base_link).data

            return Response(response, status=status.HTTP_201_CREATED)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except ObjectDoesNotExist:
            send_link.delay(
                link=link,
                user_email=user_email,
                content_base_link_uuid=str(content_base_link.uuid)
            )
            response = CreatedContentBaseLinkSerializer(content_base_link).data
            return Response(response, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        try:
            user = self.request.user
            user_email: str = user.email
            contentbaselink_uuid: str = kwargs.get('contentbaselink_uuid')
            content_base_uuid: str = kwargs.get('content_base_uuid')

            use_case = intelligences.RetrieveContentBaseLinkUseCase()
            content_base_link = use_case.get_contentbaselink(
                contentbaselink_uuid=contentbaselink_uuid,
                user_email=user_email
            )
            project_use_case = ProjectsUseCase()
            project = project_use_case.get_project_by_content_base_uuid(content_base_uuid)
            indexer = project_use_case.get_indexer_database_by_project(project)

            use_case = intelligences.DeleteContentBaseLinkUseCase(indexer)
            use_case.delete_by_object(
                content_base_link,
            )

            if project.indexer_database == Project.BEDROCK:
                start_ingestion_job.delay("", post_delete=True)

            event_manager.notify(
                event="contentbase_link_activity",
                action_type="D",
                content_base_link=content_base_link,
                user=user
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
                user=user
            )
            return Response(status=status.HTTP_204_NO_CONTENT)


class DownloadFileViewSet(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            file_name = request.data.get('file_name')
            contentbasefile_uuid = request.data.get('content_base_file')
            user_email = request.user.email

            use_case = intelligences.RetrieveContentBaseFileUseCase()
            content_base_file = use_case.get_contentbasefile(
                contentbasefile_uuid=contentbasefile_uuid,
                user_email=user_email
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
                    status=200
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

    def _create_links(
        self,
        links: list,
        user: User,
        content_base: ContentBase,
        project: Project
    ) -> list:
        created_links = []
        if links:
            for link in links:

                link_serializer = ContentBaseLinkSerializer(data={"link": link})
                link_serializer.is_valid(raise_exception=True)
                link_dto = intelligences.ContentBaseLinkDTO(
                    link=link,
                    user_email=user.email,
                    content_base_uuid=str(content_base.uuid)
                )
                content_base_link = intelligences.CreateContentBaseLinkUseCase().create_content_base_link(link_dto)

                if project.indexer_database == Project.BEDROCK:
                    bedrock_send_link.delay(
                        link=link,
                        user_email=user.email,
                        content_base_link_uuid=str(content_base_link.uuid)
                    )
                else:
                    send_link.delay(
                        link=link,
                        user_email=user.email,
                        content_base_link_uuid=str(content_base_link.uuid)
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
        content_base = use_case.get_default_by_project(
            project_uuid,
            user.email,
            is_superuser=module_permission
        )
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

        agent = {
            "agent": agent_data,
            "instructions": instructions_objects
        }
        request.data["instructions"] = instructions_objects

        new_request = request._request
        new_request.data = request.data

        personalization_serializer = ContentBasePersonalizationSerializer(
            content_base,
            data=agent,
            partial=True,
            context={"request": new_request}
        )

        if personalization_serializer.is_valid():
            personalization_serializer.save()

        project.inline_agent_switch = True
        project.save()

        response = {
            "personalization": personalization_serializer.data,
            "links": created_links
        }

        return Response(response, status=200)

    def delete(self, request, project_uuid):

        user: User = request.user
        module_permission = user.has_perm("users.can_communicate_internally")

        if not module_permission:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        use_case = intelligences.RetrieveContentBaseUseCase()
        content_base = use_case.get_default_by_project(
            project_uuid,
            user.email,
            is_superuser=module_permission
        )
        content_base_uuid: str = content_base.uuid

        use_case = intelligences.RetrieveContentBaseLinkUseCase()
        existing_links = use_case.get_content_base_link_by_link(
            content_base_uuid=content_base_uuid,
            link=request.data.get("link")
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
                start_ingestion_job.delay("", post_delete=True)

            event_manager.notify(
                event="contentbase_link_activity",
                action_type="D",
                content_base_link=link,
                user=user
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class LLMViewset(views.APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid):
        llm_config = intelligences.get_llm_config(
            project_uuid=project_uuid
        )
        return Response(
            data=LLMConfigSerializer(llm_config).data,
            status=200
        )

    def patch(self, request, project_uuid):
        user_email = request.user.email
        llm_update_dto = intelligences.UpdateLLMDTO(
            user_email=user_email,
            project_uuid=project_uuid,
            model=request.data.get("model"),
            setup=request.data.get("setup"),
            advanced_options=request.data.get("advanced_options")
        )
        usecase = intelligences.UpdateLLMUseCase()
        updated_llm = usecase.update_llm_by_project(llm_update_dto)

        return Response(
            data=LLMConfigSerializer(updated_llm).data,
            status=200
        )


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
            advanced_options={}
        )

        return Response(
            data=llm_update_dto,
            status=200
        )

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
            advanced_options={}
        )
        usecase = intelligences.UpdateLLMUseCase()
        updated_llm = usecase.update_llm_by_project(llm_update_dto)

        return Response(
            data=LLMConfigSerializer(updated_llm).data,
            status=200
        )


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
            authorization_header = request.headers.get('Authorization', "Bearer unauthorized")
            is_super_user = permissions.is_super_user(authorization_header)

            if not is_super_user:
                user_email = request.user.email

            project_uuid = kwargs.get('project_uuid')

            content_base = intelligences.RetrieveContentBaseUseCase().get_default_by_project(project_uuid, user_email, is_super_user)
            data = ContentBasePersonalizationSerializer(content_base, context={"request": request, "project_uuid": project_uuid}).data
            return Response(data=data, status=status.HTTP_200_OK)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def update(self, request, *args, **kwargs):
        try:
            project_uuid = kwargs.get('project_uuid')
            content_base = intelligences.RetrieveContentBaseUseCase().get_default_by_project(project_uuid, request.user.email)

            context = {
                "request": request,
                "project_uuid": project_uuid
            }

            if 'team_data' in request.data:
                request.data['team'] = request.data.pop('team_data')

            serializer = ContentBasePersonalizationSerializer(
                content_base,
                data=request.data,
                partial=True,
                context=context
            )

            if serializer.is_valid():
                serializer.save()
                data = serializer.data
                return Response(data=data, status=status.HTTP_200_OK)
            else:
                print("Serializer errors:", serializer.errors)
                return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            print(f"Error updating personalization: {str(e)}")
            return Response(
                data={"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def destroy(self, request, *args, **kwargs):
        try:
            instruction_id = request.query_params.get("id")
            project_uuid = kwargs.get('project_uuid')
            content_base = intelligences.RetrieveContentBaseUseCase().get_default_by_project(project_uuid, request.user.email)
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
                page_number=page_number
            )
            return Response(data=response, status=200)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return Response(data={"message": str(e)}, status=500)


class UploadFileView(views.APIView):
    permission_classes = [ProjectPermission]

    def post(self, request, *args, **kwargs):

        file = request.FILES.get('file')
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
                    }
                },
                status=status.HTTP_200_OK
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
                        "links": links
                    }
                },
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {
                    "message": "The agent isn't configured!",
                    "data": {
                        "has_agent": False,
                    }
                },
                status=status.HTTP_200_OK
            )


class TopicsViewSet(ModelViewSet):
    serializer_class = TopicsSerializer
    permission_classes = [CombinedExternalProjectPermission]
    authentication_classes = []  # Disable default authentication
    lookup_field = 'uuid'

    def get_queryset(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            return Topics.objects.none()  # pragma: no cover

        project_uuid = self.kwargs.get('project_uuid')
        if project_uuid:
            return Topics.objects.filter(project__uuid=project_uuid)
        return Topics.objects.none()

    def create(self, request, *args, **kwargs):
        project_uuid = self.kwargs.get('project_uuid')
        if not project_uuid:
            return Response(
                {"error": "project_uuid is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            return Response(
                {"error": "Project not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(project=project)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SubTopicsViewSet(ModelViewSet):
    serializer_class = SubTopicsSerializer
    permission_classes = [CombinedExternalProjectPermission]
    authentication_classes = []  # Disable default authentication
    lookup_field = 'uuid'

    def get_queryset(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            return SubTopics.objects.none()  # pragma: no cover

        topic_uuid = self.kwargs.get('topic_uuid')
        if topic_uuid:
            return SubTopics.objects.filter(topic__uuid=topic_uuid)
        return SubTopics.objects.none()

    def create(self, request, *args, **kwargs):
        topic_uuid = self.kwargs.get('topic_uuid')
        if not topic_uuid:
            return Response(
                {"error": "topic_uuid is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            topic = Topics.objects.get(uuid=topic_uuid)
        except Topics.DoesNotExist:
            return Response(
                {"error": "Topic not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(topic=topic)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SupervisorViewset(ModelViewSet):
    serializer_class = SupervisorDataSerializer
    permission_classes = [CombinedExternalProjectPermission]
    pagination_class = SupervisorPagination
    lookup_field = 'uuid'

    def _parse_boolean_param(self, value: str) -> bool:
        """Parse boolean parameter from string"""
        return value.lower() in ['true', '1', 'yes']

    def _apply_filters_to_data(self, data, request):
        """Apply filters to unified data structure - only for billing data since conversations are filtered at DB level"""
        # Note: csat, topic, has_chats_room filters are applied at database level for conversations
        # This method is mainly for any future filters that might apply to both conversation and billing data

        # Apply search filter to billing data
        search = request.query_params.get('search')
        if search:
            search_lower = search.lower()
            data = [
                item for item in data
                if (str(item.get('name') or '').lower().find(search_lower) != -1 or
                    str(item.get('urn') or '').lower().find(search_lower) != -1)
            ]

        # Apply resolution filter only to billing data (conversation data is already filtered at DB level)
        resolution = request.query_params.get('resolution')
        if resolution:
            resolution_values = [value.strip() for value in resolution.split(',')]
            data = [
                item for item in data
                if ((item.get('is_billing_only', False) and 
                     str(item.get('resolution', '')) in resolution_values) or
                    (not item.get('is_billing_only', False)))  # Keep conversation data as it's already filtered
            ]

        return data

    def _convert_conversation_to_unified(self, conversation):

        unified_object = {
            "created_on": conversation.created_at,
            "urn": conversation.contact_urn,
            "uuid": conversation.uuid,
            "external_id": conversation.external_id,
            "csat": conversation.csat,
            "nps": conversation.nps,
            "topic": conversation.topic.name if conversation.topic else None,
            "has_chats_room": conversation.has_chats_room,
            "start_date": conversation.start_date or conversation.created_at,  # Use created_at as fallback
            "end_date": conversation.end_date,  # Use created_at as fallback
            "resolution": conversation.resolution,
            "name": conversation.contact_name,
            "is_billing_only": False
        }

        return unified_object

    def _has_conversation_specific_filters(self, request):
        """Check if any filters that only apply to conversation data are being used"""
        conversation_specific_params = ['csat', 'topic', 'has_chats_room', 'resolution']
        return any(request.query_params.get(param) for param in conversation_specific_params)

    def _build_conversation_filters(self, request):
        """Build database filters for conversation query based on request parameters"""
        filters = {}

        # CSAT filter
        csat = request.query_params.get('csat')
        if csat:
            if isinstance(csat, str):
                csat_values = [value.strip() for value in csat.split(',')]
            else:
                csat_values = [csat]
            filters['csat__in'] = csat_values

        # Resolution filter - always apply to conversation data at database level
        resolution = request.query_params.get('resolution')
        if resolution:
            if isinstance(resolution, str):
                # Parse comma-separated resolution values
                resolution_values = [value.strip() for value in resolution.split(',')]
            else:
                resolution_values = [str(resolution)]

            # Convert string values to integers for database filtering
            # Django stores the first value of choices (integer) in the database
            resolution_int_values = []
            for value in resolution_values:
                try:
                    resolution_int_values.append(int(value))
                except ValueError:
                    # If conversion fails, keep the original value
                    resolution_int_values.append(value)

            # Always apply database-level filtering for conversations
            # Billing data will be filtered at application level
            filters['resolution__in'] = resolution_int_values

        # Topic filter
        topic = request.query_params.get('topic')
        if topic:
            if isinstance(topic, str):
                topic_values = [value.strip() for value in topic.split(',')]
            else:
                topic_values = [topic]
            filters['topic__name__in'] = topic_values

        # Has chats room filter
        has_chats_room = request.query_params.get('has_chats_room')
        if has_chats_room is not None:
            has_chats_room_bool = self._parse_boolean_param(has_chats_room)
            filters['has_chats_room'] = has_chats_room_bool

        search = request.query_params.get('search')
        if search:
            from django.db.models import Q
            filters['Q'] = Q(contact_name__icontains=search) | Q(contact_urn__icontains=search)

        nps = request.query_params.get('nps')
        if nps:
            filters['nps'] = nps

        return filters

    def list(self, request, *args, **kwargs):
        """Get all supervisor data combining both Conversation model data and billing data"""
        project_uuid = kwargs.get('project_uuid')
        if not project_uuid:
            return Response(
                {"error": "project_uuid is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            project = get_project_by_uuid(project_uuid)

            start_date = request.query_params.get(
                'start_date',
                pendulum.now().subtract(days=30).to_date_string()
            )
            end_date = request.query_params.get('end_date') or request.query_params.get('end_date')
            if not end_date:
                end_date = pendulum.now().to_date_string()

            # Convert DD-MM-YYYY to YYYY-MM-DD for Django date filtering
            try:
                from datetime import datetime
                start_date_obj = datetime.strptime(start_date, '%d-%m-%Y')
                end_date_obj = datetime.strptime(end_date, '%d-%m-%Y')
                start_datetime = start_date_obj.date()
                end_datetime = end_date_obj.date()
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Expected DD-MM-YYYY format"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get conversation data with database-level filtering
            conversation_filters = self._build_conversation_filters(request)

            # Handle Q object for search filtering
            q_object = conversation_filters.pop('Q', None)

            conversation_queryset = Conversation.objects.select_related('topic', 'project').filter(
                project=project,
                created_at__date__gte=start_datetime,
                created_at__date__lte=end_datetime,
                **conversation_filters
            )

            # Apply Q object if search filter is used
            if q_object:
                conversation_queryset = conversation_queryset.filter(q_object)

            # Add distinct to remove duplicates based on uuid
            conversation_queryset = conversation_queryset.distinct('uuid').order_by('uuid', '-created_at')

            conversation_data = list(conversation_queryset)

            unified_conversation_data = [
                self._convert_conversation_to_unified(conv) for conv in conversation_data
            ]

            # Check if there are conversation-only filters (excluding resolution)
            conversation_only_params = ['csat', 'topic', 'has_chats_room']
            has_conversation_only_filters = any(request.query_params.get(param) for param in conversation_only_params)

            if has_conversation_only_filters:
                # If conversation-only filters are used, only return conversation data
                # This applies even if resolution=3 is requested or search is used
                all_data = unified_conversation_data
            else:
                # Fetch billing data if no conversation-specific filters OR if search is used OR if in_progress is requested
                if start_date and end_date:
                    supervisor = Supervisor()

                    # Extract Bearer token from Authorization header
                    auth_header = request.headers.get('Authorization', '')
                    user_token = ""
                    if auth_header.startswith('Bearer '):
                        user_token = auth_header.split('Bearer ')[1]

                    billing_data = supervisor.get_supervisor_data_by_date(
                        project_uuid=project_uuid,
                        start_date=start_date,
                        end_date=end_date,
                        page=1,  # Get all data
                        user_token=user_token,
                        search=request.query_params.get('search')
                    )

                    # Supervisor class already filters out billing data that has conversation data
                    # So we can directly combine both data sources
                    all_data = unified_conversation_data + billing_data
                else:
                    all_data = unified_conversation_data

            # Apply any remaining filters and sort
            all_data = self._apply_filters_to_data(all_data, request)
            all_data.sort(key=lambda x: x.get('created_on', ''), reverse=True)

            # Apply pagination
            page = self.paginate_queryset(all_data)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            # Fallback if pagination is not configured
            serializer = self.get_serializer(all_data, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ProjectDoesNotExist:
            return Response(
                {"error": f"Project with UUID {project_uuid} not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.capture_exception(e)

            print(f"Error retrieving supervisor data: {str(e)}")
            return Response(
                {"error": f"Error retrieving supervisor data: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
