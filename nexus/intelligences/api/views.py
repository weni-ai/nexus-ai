from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin
from rest_framework.pagination import CursorPagination

from .serializers import IntelligenceSerializer
from nexus.usecases.intelligences import ListIntelligencesUseCases


class CustomCursorPagination(CursorPagination):
    page_size = 10
    ordering = "created_at"


class IntelligecesViewset(ListModelMixin, GenericViewSet):

    serializer_class = IntelligenceSerializer
    pagination_class = CustomCursorPagination

    def get_queryset(self):
        use_case = ListIntelligencesUseCases()
        org_uuid = self.kwargs.get('org_uuid')
        return use_case.get_org_intelligences(org_uuid)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
