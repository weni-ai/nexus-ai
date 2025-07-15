from rest_framework import views, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .serializers import ProjectSerializer

from nexus.usecases.projects.update import ProjectUpdateUseCase
from nexus.usecases.projects.dto import UpdateProjectDTO
from nexus.usecases.projects.retrieve import get_project
from nexus.projects.api.permissions import ProjectPermission
from nexus.usecases.projects.projects_use_case import ProjectsUseCase


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

class ProjectPromptCreationConfigurationsViewset(views.APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid):
        configurations = ProjectsUseCase().get_project_prompt_creation_configurations(
            project_uuid=project_uuid
        )
        return Response(configurations)

    def patch(self, request, project_uuid):
        configurations = ProjectsUseCase().set_project_prompt_creation_configurations(
            project_uuid=project_uuid,
            use_prompt_creation_configurations=request.data.get('use_prompt_creation_configurations'),
            conversation_turns_to_include=request.data.get('conversation_turns_to_include'),
            exclude_previous_thinking_steps=request.data.get('exclude_previous_thinking_steps')
        )

        return Response(configurations)