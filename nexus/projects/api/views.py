from rest_framework import views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .serializers import UpdateProjectSerializer

from nexus.usecases import projects


class ProjectUpdateViewset(views.APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, project_uuid):
        user_email = request.user.email
        dto = projects.UpdateProjectDTO(
            user_email,
            project_uuid,
            brain_on=request.data.get('brain_on')
        )
        updated_project = projects.update_project(dto)

        return Response(
            UpdateProjectSerializer(updated_project).data
        )
