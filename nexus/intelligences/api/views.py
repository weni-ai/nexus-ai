from rest_framework import status
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import (
    ListModelMixin,
    CreateModelMixin,
    UpdateModelMixin
)
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response

from .serializers import IntelligenceSerializer
from nexus.usecases.intelligences import (
    ListIntelligencesUseCase,
    CreateIntelligencesUseCase,
    UpdateIntelligenceUseCase,
    DeleteIntelligenceUseCase
)


class CustomCursorPagination(CursorPagination):
    page_size = 10
    ordering = "created_at"


class IntelligecesViewset(
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
