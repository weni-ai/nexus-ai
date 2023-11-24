from rest_framework import status
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import (
    ListModelMixin,
    CreateModelMixin,
    UpdateModelMixin
)
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response

from .serializers import (
    IntelligenceSerializer,
    ContentBaseSerializer,
    ContentBaseTextSerializer
)
from nexus.usecases.intelligences import (
    ListIntelligencesUseCase,
    CreateIntelligencesUseCase,
    UpdateIntelligenceUseCase,
    DeleteIntelligenceUseCase,
    ListContentBaseUseCase,
    CreateContentBaseUseCase,
    UpdateContentBaseUseCase,
    DeleteContentBaseUseCase,
    ListContentBaseTextUseCase,
    CreateContentBaseTextUseCase,
    UpdateContentBaseTextUseCase,
    DeleteContentBaseTextUseCase
)


class CustomCursorPagination(CursorPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50
    ordering = "created_at"


class IntelligencesViewset(
    ListModelMixin,
    CreateModelMixin,
    UpdateModelMixin,
    GenericViewSet
):

    serializer_class = IntelligenceSerializer
    pagination_class = CustomCursorPagination

    def get_queryset(self):
        use_case = ListIntelligencesUseCase()
        org_uuid = self.kwargs.get('org_uuid')
        return use_case.get_org_intelligences(org_uuid)

    def create(self, request, org_uuid=str):
        use_case = CreateIntelligencesUseCase()

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
        use_case = UpdateIntelligenceUseCase()

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
        use_case = DeleteIntelligenceUseCase()

        intelligence_uuid = request.data.get('intelligence_uuid')

        use_case.delete_intelligences(
            intelligence_uuid=intelligence_uuid
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


class ContentBaseViewset(
    ListModelMixin,
    CreateModelMixin,
    UpdateModelMixin,
    GenericViewSet
):

    pagination_class = CustomCursorPagination
    serializer_class = ContentBaseSerializer

    def get_queryset(self):
        use_case = ListContentBaseUseCase()
        intelligence_uuid = self.kwargs.get('intelligence_uuid')
        return use_case.get_intelligence_contentbases(intelligence_uuid)

    def create(self, request, intelligence_uuid=str):
        use_case = CreateContentBaseUseCase()

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
        use_case = UpdateContentBaseUseCase()

        update_contentbase = use_case.update_contentbase(
            contentbase_uuid=request.data.get('contentbase_uuid'),
            title=request.data.get('title')
        )

        return Response(
            ContentBaseSerializer(update_contentbase).data,
            status=status.HTTP_200_OK
        )

    def destroy(self, request):
        use_case = DeleteContentBaseUseCase()

        contentbase_uuid = request.data.get('contentbase_uuid')

        use_case.delete_contentbase(
            contentbase_uuid=contentbase_uuid
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


class ContentBaseTextViewset(
    ListModelMixin,
    CreateModelMixin,
    UpdateModelMixin,
    GenericViewSet
):

    pagination_class = CustomCursorPagination
    serializer_class = ContentBaseTextSerializer

    def get_queryset(self):
        use_case = ListContentBaseTextUseCase()
        contentbase_uuid = self.kwargs.get('contentbase_uuid')
        return use_case.get_contentbase_contentbasetexts(contentbase_uuid)

    def create(self, request, contentbase_uuid=str):
        use_case = CreateContentBaseTextUseCase()

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
        use_case = UpdateContentBaseTextUseCase()

        update_contentbasetext = use_case.update_contentbasetext(
            contentbasetext_uuid=request.data.get('contentbasetext_uuid'),
            text=request.data.get('text')
        )

        return Response(
            ContentBaseTextSerializer(update_contentbasetext).data,
            status=status.HTTP_200_OK
        )

    def destroy(self, request):
        use_case = DeleteContentBaseTextUseCase()

        contentbasetext_uuid = request.data.get('contentbasetext_uuid')

        use_case.delete_contentbasetext(
            contentbasetext_uuid=contentbasetext_uuid
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT
)