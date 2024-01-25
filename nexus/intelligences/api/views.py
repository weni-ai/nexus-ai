from django.core.exceptions import PermissionDenied
from django.utils.datastructures import MultiValueDictKeyError

from rest_framework import status, parsers, views
from rest_framework.viewsets import ModelViewSet
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from nexus.usecases.intelligences.exceptions import IntelligencePermissionDenied
from .serializers import (
    IntelligenceSerializer,
    ContentBaseSerializer,
    ContentBaseTextSerializer,
    ContentBaseFileSerializer
)
from nexus.usecases import intelligences
from nexus.orgs import permissions
from nexus.intelligences.models import Intelligence, ContentBase, ContentBaseText, ContentBaseFile

from nexus.task_managers.file_database.s3_file_database import s3FileDatabase
from nexus.task_managers.file_manager.celery_file_manager import CeleryFileManager
from nexus.task_managers.tasks import upload_text_file
from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase
from nexus.usecases import intelligences
from nexus.task_managers.models import ContentBaseFileTaskManager
from nexus.usecases.orgs.get_by_uuid import get_org_by_content_base_uuid


class CustomCursorPagination(CursorPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50
    ordering = "created_at"


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

    def create(self, request, org_uuid=str):
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
        intelligence_usecase = intelligences.IntelligenceGenerativeSearchUseCase()
        return Response(
            data=intelligence_usecase.search(content_base_uuid=data.get("content_base_uuid"), text=data.get("text"), language=data.get("language")),
            status=200
        )


class QuickTestAIAPIView(views.APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        try:
            
            data = request.data
            content_base_uuid=data.get("content_base_uuid")

            user = request.user
            org = get_org_by_content_base_uuid(content_base_uuid)
            has_permission = permissions.can_list_content_bases(user, org)

            if has_permission:
                intelligence_usecase = intelligences.IntelligenceGenerativeSearchUseCase()
                return Response(
                    data=intelligence_usecase.search(content_base_uuid=content_base_uuid, text=data.get("text"), language=data.get("language")),
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
        sentenx_status = [ContentBaseFileTaskManager.STATUS_SUCCESS, ContentBaseFileTaskManager.STATUS_FAIL]
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

    def create(self, request, intelligence_uuid=str):
        try:
            user_email = request.user.email
            use_case = intelligences.CreateContentBaseUseCase()

            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            title = serializer.validated_data.get('title')
            description = serializer.validated_data.get('description')

            contentbase = use_case.create_contentbase(
                intelligence_uuid=intelligence_uuid,
                title=title,
                user_email=user_email,
                description=description
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
            contentbasetext_uuid = kwargs.get('content_base_text_uuid')

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
            )
            cbt_dto = intelligences.ContentBaseTextDTO(
                text=text,
                content_base_uuid=content_base_uuid,
                user_email=user_email
            )
            content_base_text = intelligences.CreateContentBaseTextUseCase.create_contentbasetext(
                content_base_dto=cb_dto,
                content_base_text_dto=cbt_dto
            )

            upload_text_file.delay(
                cb_dto=cb_dto,
                cbt=content_base_text
            )

            response = ContentBaseTextSerializer(content_base_text).data

            return Response(
                response,
                status=status.HTTP_201_CREATED
            )
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def update(self, request, **kwargs):
        try:
            user_email = request.user.email
            text = request.data.get('text')
            content_base_uuid = kwargs.get('content_base_uuid')

            content_base = intelligences.get_by_contentbase_uuid(content_base_uuid)
            cb_dto = intelligences.ContentBaseDTO(
                uuid=content_base.uuid,
                title=content_base.title,
                intelligence_uuid=content_base.intelligence.uuid,
            )
            cbt_dto = intelligences.ContentBaseTextDTO(
                text=text,
                content_base_uuid=content_base_uuid,
                user_email=user_email
            )
            content_base_text = intelligences.UpdateContentBaseTextUseCase.update_contentbasetext(
                content_base_dto=cb_dto,
                content_base_text_dto=cbt_dto
            )

            upload_text_file.delay(
                cb_dto=cb_dto,
                cbt=content_base_text
            )

            response = ContentBaseTextSerializer(content_base_text).data

            return Response(
                response,
                status=status.HTTP_200_OK
            )
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def destroy(self, request, **kwargs):
        try:
            user_email = request.user.email
            use_case = intelligences.DeleteContentBaseTextUseCase()

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

        try:
            file = request.FILES['file']
            self.get_queryset()
            user_email = request.user.email
            extension_file = request.data.get("extension_file")
            file_database = s3FileDatabase()
            file_manager = CeleryFileManager(file_database=file_database)
            response = file_manager.upload_file(file, content_base_uuid, extension_file, user_email)

            return Response(
                response,
                status=status.HTTP_201_CREATED
            )
        except MultiValueDictKeyError:
            return Response(data={"message": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
        except IntelligencePermissionDenied:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

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
