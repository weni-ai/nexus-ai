import json
import boto3
from typing import Dict, List
from io import BytesIO

from django.conf import settings
from django.template.defaultfilters import slugify

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from nexus.inline_agents.models import Agent
from nexus.usecases.agents.exceptions import SkillFileTooLarge
from nexus.usecases.inline_agents.create import CreateAgentUseCase
from nexus.projects.models import Project


SKILL_FILE_SIZE_LIMIT = 10


class PushAgents(APIView):
    permission_classes = [IsAuthenticated]

    def _validate_request(self, request):
        """Validate request data and return processed inputs"""
        def validate_file_size(files):
            for file in files:
                if files[file].size > SKILL_FILE_SIZE_LIMIT * (1024**2):
                    raise SkillFileTooLarge(file)

        files = request.FILES
        validate_file_size(files)

        agents = json.loads(request.data.get("agents"))
        project_uuid = request.data.get("project_uuid")

        return files, agents, project_uuid


    def post(self, request, *args, **kwargs):
        agent_usecase = CreateAgentUseCase()
        files, agents, project_uuid = self._validate_request(request)
        agents = agents["agents"]

        try:
            project = Project.objects.get(uuid=project_uuid)
            for key in agents:
                agent = agents[key]
                agent_usecase.create_agent(agent, project, files)

        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)

        return Response({})
