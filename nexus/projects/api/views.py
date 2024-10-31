from rest_framework import views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .serializers import ProjectSerializer

from nexus.usecases.projects.update import ProjectUpdateUseCase
from nexus.usecases.projects.dto import UpdateProjectDTO
from nexus.usecases.projects.retrieve import get_project


class ProjectUpdateViewset(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        user_email = request.user.email
        project = get_project(project_uuid, user_email)

        return Response(
            ProjectSerializer(project).data
        )

    def patch(self, request, project_uuid):
        user_email = request.user.email
        dto = UpdateProjectDTO(
            user_email,
            project_uuid,
            brain_on=request.data.get('brain_on')
        )
        usecase = ProjectUpdateUseCase()
        updated_project = usecase.update_project(dto)

        return Response(
            ProjectSerializer(updated_project).data
        )


class ProjectIndexerView(views.APIView):
    def post(self, request, project_uuid):
        user_email = request.user.email
        indexer_database = request.data.get("indexer")

        ProjectUpdateUseCase().migrate_project(
            project_uuid=project_uuid,
            indexer_database=indexer_database,
            user_email=user_email
        )

        return Response({})
