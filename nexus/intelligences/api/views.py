from django.core.exceptions import PermissionDenied
from django.conf import settings

from rest_framework import status, parsers, views
from rest_framework.viewsets import ModelViewSet
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response

from .serializers import (
    IntelligenceSerializer,
    ContentBaseSerializer,
    ContentBaseTextSerializer,
    ContentBaseFileSerializer
)
from nexus.usecases import intelligences
from nexus.orgs import permissions
from nexus.task_managers.file_database.s3_file_database import s3FileDatabase
from nexus.task_managers.file_manager.celery_file_manager import CeleryFileManager
from nexus.intelligences.models import Intelligence, ContentBase, ContentBaseText, ContentBaseFile


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

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Intelligence.objects.none()  # pragma: no cover
        use_case = intelligences.ListIntelligencesUseCase()
        org_uuid = self.kwargs.get('org_uuid')
        use_case_list = use_case.get_org_intelligences(
            org_uuid
        )

        return use_case_list

    def retrieve(self, request, *args, **kwargs):
        intelligence_uuid = kwargs.get('intelligence_uuid')
        use_case = intelligences.RetrieveIntelligenceUseCase()
        intelligence = use_case.get_intelligence(
            intelligence_uuid=intelligence_uuid
        )
        serializer = IntelligenceSerializer(intelligence)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, org_uuid=str):
        use_case = intelligences.CreateIntelligencesUseCase()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_email = request.data.get("email")
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

    def update(self, request):
        use_case = intelligences.UpdateIntelligenceUseCase()

        update_intelligence = use_case.update_intelligences(
            intelligence_uuid=request.data.get('intelligence_uuid'),
            name=request.data.get('name'),
            description=request.data.get('description')
        )

        return Response(
            IntelligenceSerializer(update_intelligence).data,
            status=status.HTTP_200_OK
        )

    def destroy(self, request):
        use_case = intelligences.DeleteIntelligenceUseCase()

        intelligence_uuid = request.data.get('intelligence_uuid')

        use_case.delete_intelligences(
            intelligence_uuid=intelligence_uuid
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


class FlowsIntelligencesApiView(views.APIView):
    
    def get(self, request, project_uuid):
        authorization_header = request.headers.get('Authorization')
        if not permissions.is_super_user(authorization_header):
            raise PermissionDenied("You has not permission to do that.")
        list_use_case = intelligences.ListAllIntelligenceContentUseCase()
        return Response(data=list_use_case.get_project_intelligences(project_uuid=project_uuid), status=200)


class GenerativeIntelligenceQuestionAPIView(views.APIView):

    def post(self, request):
        authorization_header = request.headers.get("Authorization")
        if not permissions.is_super_user(authorization_header):
            return PermissionDenied("You has not permission to do that.")
        data = request.data
        intelligence_usecase = intelligences.IntelligenceGenerativeSearchUseCase()
        return Response(
            data=intelligence_usecase.search(content_base_uuid=data.get("content_base_uuid"), text=data.get("text")),
            status=200
        )
        



class ContentBaseViewset(
    ModelViewSet
):

    pagination_class = CustomCursorPagination
    serializer_class = ContentBaseSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContentBase.objects.none()  # pragma: no cover
        use_case = intelligences.ListContentBaseUseCase()
        intelligence_uuid = self.kwargs.get('intelligence_uuid')
        use_case_list = use_case.get_intelligence_contentbases(
            intelligence_uuid
        )
        return use_case_list

    def retrieve(self, request, *args, **kwargs):

        contentbase_uuid = kwargs.get('content_base_uuid')
        use_case = intelligences.RetrieveContentBaseUseCase()
        contentbase = use_case.get_contentbase(
            contentbase_uuid=contentbase_uuid
        )
        serializer = ContentBaseSerializer(contentbase)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, intelligence_uuid=str):
        use_case = intelligences.CreateContentBaseUseCase()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        title = serializer.validated_data.get('title')
        user_email = request.data.get("email")

        contentbase = use_case.create_contentbase(
            intelligence_uuid=intelligence_uuid,
            title=title,
            user_email=user_email
        )

        return Response(
            ContentBaseSerializer(contentbase).data,
            status=status.HTTP_201_CREATED
        )

    def update(self, request):
        use_case = intelligences.UpdateContentBaseUseCase()

        update_contentbase = use_case.update_contentbase(
            contentbase_uuid=request.data.get('contentbase_uuid'),
            title=request.data.get('title')
        )

        return Response(
            ContentBaseSerializer(update_contentbase).data,
            status=status.HTTP_200_OK
        )

    def destroy(self, request):
        use_case = intelligences.DeleteContentBaseUseCase()

        contentbase_uuid = request.data.get('contentbase_uuid')

        use_case.delete_contentbase(
            contentbase_uuid=contentbase_uuid
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


class ContentBaseTextViewset(
    ModelViewSet
):

    pagination_class = CustomCursorPagination
    serializer_class = ContentBaseTextSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContentBaseText.objects.none()  # pragma: no cover
        use_case = intelligences.ListContentBaseTextUseCase()
        contentbase_uuid = self.kwargs.get('contentbase_uuid')
        use_case_list = use_case.get_contentbase_contentbasetexts(
            contentbase_uuid
        )
        return use_case_list

    def retrieve(self, request, *args, **kwargs):

        contentbasetext_uuid = kwargs.get('content_base_text_uuid')
        use_case = intelligences.RetrieveContentBaseTextUseCase()
        contentbasetext = use_case.get_contentbasetext(
            contentbasetext_uuid=contentbasetext_uuid
        )
        serializer = ContentBaseTextSerializer(contentbasetext)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, contentbase_uuid=str):
        use_case = intelligences.CreateContentBaseTextUseCase()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        text = serializer.validated_data.get('text')
        user_email = request.data.get("email")

        contentbasetext = use_case.create_contentbasetext(
            contentbase_uuid=contentbase_uuid,
            text=text,
            user_email=user_email
        )

        return Response(
            ContentBaseTextSerializer(contentbasetext).data,
            status=status.HTTP_201_CREATED
        )

    def update(self, request):
        use_case = intelligences.UpdateContentBaseTextUseCase()

        update_contentbasetext = use_case.update_contentbasetext(
            contentbasetext_uuid=request.data.get('contentbasetext_uuid'),
            text=request.data.get('text')
        )

        return Response(
            ContentBaseTextSerializer(update_contentbasetext).data,
            status=status.HTTP_200_OK
        )

    def destroy(self, request):
        use_case = intelligences.DeleteContentBaseTextUseCase()

        contentbasetext_uuid = request.data.get('contentbasetext_uuid')

        use_case.delete_contentbasetext(
            contentbasetext_uuid=contentbasetext_uuid
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


class ContentBaseFileViewset(ModelViewSet):
    
    serializer_class = ContentBaseFileSerializer
    pagination_class = CustomCursorPagination
    parser_classes = (parsers.MultiPartParser,)

    def create(self, request, content_base_uuid=str):
        file = request.FILES['file']
        
        user_email = request.data.get("user_email")
        extension_file = request.data.get("extension_file")
        file_database = s3FileDatabase()
        file_manager = CeleryFileManager(file_database=file_database)
        response = file_manager.upload_file(file, content_base_uuid, extension_file, user_email)
        
        return Response(
            response,
            status=status.HTTP_201_CREATED
        )

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ContentBaseFile.objects.none()  # pragma: no cover
        use_case = intelligences.ListContentBaseFileUseCase()
        contentbase_uuid = self.kwargs.get('content_base_uuid')
        print(f"contentbase_uuid: {contentbase_uuid}")
        return use_case.get_contentbase_file(contentbase_uuid=contentbase_uuid)

    def retrieve(self, request, *args, **kwargs):

        contentbasefile_uuid = kwargs.get('contentbase_file_uuid')
        use_case = intelligences.RetrieveContentBaseFileUseCase()
        contentbasetext = use_case.get_contentbasefile(
            contentbasefile_uuid=contentbasefile_uuid
        )
        serializer = ContentBaseTextSerializer(contentbasetext)
        return Response(serializer.data, status=status.HTTP_200_OK)

    
