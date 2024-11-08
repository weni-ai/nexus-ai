from rest_framework import views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .serializers import ProjectSerializer

from nexus.usecases.projects.update import ProjectUpdateUseCase
from nexus.usecases.projects.dto import UpdateProjectDTO
from nexus.usecases.projects.retrieve import get_project
from nexus.usecases.logs.retrieve import RetrieveMessageUseCase
from nexus.usecases.logs.create import CreateLogUsecase

from nexus.projects.api.serializers import MessageDetailSerializer
from nexus.projects.api.permissions import ProjectPermission


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


class MessageDetailViewSet(views.APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid, message_uuid):
        message = RetrieveMessageUseCase().get_by_uuid(message_uuid)
        return Response(MessageDetailSerializer(message).data)

    def patch(self, request, project_uuid, message_uuid):
        data = request.data
        usecase = CreateLogUsecase()
        usecase.message = RetrieveMessageUseCase().get_by_uuid(message_uuid)
        usecase.log = usecase.message.messagelog

        serializer = MessageDetailSerializer(usecase.message, data=data, partial=True)
        serializer.is_valid()

        usecase.update_log_field(**data)
        keys = list(data.keys())
        response_data = {}

        for key in keys:
            response_data.update(
                {
                    key: getattr(usecase.log, key)
                }
            )
        return Response(response_data)
