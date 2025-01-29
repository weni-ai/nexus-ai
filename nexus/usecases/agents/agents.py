from typing import Dict, List, Tuple
from dataclasses import dataclass, field

from django.conf import settings
from django.template.defaultfilters import slugify

from nexus.users.models import User
from nexus.agents.models import (
    ActiveAgent,
    Agent,
    AgentSkills,
    Team,
    AgentVersion
)
from nexus.projects.models import Project
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase, BedrockSubAgent
from nexus.task_managers.tasks_bedrock import run_create_lambda_function, run_update_lambda_function

from nexus.usecases.agents.exceptions import (
    AgentInstructionsTooShort,
    AgentNameTooLong,
    SkillNameTooLong,
    AgentAttributeNotAllowed
)


@dataclass
class AgentDTO:
    slug: str
    name: str
    description: str
    instructions: List[str]
    guardrails: List[str]
    skills: List[Dict]
    model: List[str]
    tags: Dict = field(default_factory=dict)
    prompt_override_configuration: Dict = field(default_factory=dict)
    memory_configuration: Dict = field(default_factory=dict)
    idle_session_tll_in_seconds: int = 1800


@dataclass
class UpdateAgentDTO:
    name: str
    slug: str = None
    skills: List[Dict] = None
    instructions: str = None
    guardrails: List[str] = None
    description: str = None
    memory_configuration: dict = None
    prompt_override_configuration: dict = None
    idle_session_ttl_in_seconds: int = None
    guardrail_configuration: dict = None
    foundation_model: str = None
    model: List[str] = None

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}


class AgentUsecase:
    def __init__(self, external_agent_client=BedrockFileDatabase):
        self.external_agent_client = external_agent_client()

    def assign_agent(self, agent_uuid: str, project_uuid: str, created_by):
        agent: Agent = self.get_agent_object(uuid=agent_uuid)
        team: Team = self.get_team_object(project__uuid=project_uuid)

        sub_agent = BedrockSubAgent(
            display_name=agent.display_name,
            slug=agent.slug,
            external_id=agent.external_id,
            alias_arn=agent.current_version.metadata.get("agent_alias"),
        )

        agent_collaborator_id = self.external_agent_client.associate_sub_agents(
            supervisor_id=team.external_id,
            agents_list=[sub_agent]
        )

        active_agent, created = ActiveAgent.objects.get_or_create(
            agent=agent,
            team=team,
            is_official=agent.is_official,
            created_by=created_by,
            metadata={"agent_collaborator_id": agent_collaborator_id}
        )
        return active_agent

    def create_agent(self, user: User, agent_dto: AgentDTO, project_uuid: str, alias_name: str = "v1"):
        print("----------- STARTING CREATE AGENT ---------")

        def format_instructions(instructions: List[str]):
            return "\n".join(instructions)

        all_instructions = agent_dto.instructions + agent_dto.guardrails

        external_id = self.create_external_agent(
            agent_name=f"{agent_dto.slug}-project-{project_uuid}",
            agent_description=agent_dto.description,
            agent_instructions=format_instructions(all_instructions),
            idle_session_tll_in_seconds=agent_dto.idle_session_tll_in_seconds,
            memory_configuration=agent_dto.memory_configuration,
            prompt_override_configuration=agent_dto.prompt_override_configuration,
            tags=agent_dto.tags,
            model_id=agent_dto.model[0],
        )

        self.external_agent_client.agent_for_amazon_bedrock.wait_agent_status_update(external_id)

        self.prepare_agent(external_id)

        self.external_agent_client.agent_for_amazon_bedrock.wait_agent_status_update(external_id)

        sub_agent_alias_id, sub_agent_alias_arn, agent_alias_version = self.create_external_agent_alias(
            agent_id=external_id, alias_name=alias_name
        )

        agent_version = self.external_agent_client.get_agent_version(external_id)

        agent = Agent.objects.create(
            created_by=user,
            project_id=project_uuid,
            external_id=external_id,
            slug=agent_dto.slug,
            display_name=agent_dto.name,
            model=agent_dto.model,
            description=agent_dto.description,
            metadata={
                "engine": "BEDROCK",
                "external_id": external_id,
                "agent_alias_id": sub_agent_alias_id,
                "agent_alias_arn": sub_agent_alias_arn,
                "agentVersion": str(agent_version),
            }
        )

        agent.versions.create(
            alias_id=sub_agent_alias_id,
            alias_name=alias_name,
            metadata={"agent_alias": sub_agent_alias_arn},
            created_by=user,
        )

        return agent

    def create_external_agent(
        self,
        agent_name: str,
        agent_description: str,
        agent_instructions: str,
        model_id: str = None,
        idle_session_tll_in_seconds: int = 1800,
        memory_configuration: Dict = {},
        tags: Dict = {},
        prompt_override_configuration: List[Dict] = []
    ):
        return self.external_agent_client.create_agent(
            agent_name,
            agent_description,
            agent_instructions,
            model_id,
            idle_session_tll_in_seconds,
            memory_configuration,
            tags,
            prompt_override_configuration,
        )

    def create_external_agent_alias(self, agent_id: str, alias_name: str) -> Tuple[str, str, str]:
        agent_alias_id, agent_alias_arn, agent_alias_version = self.external_agent_client.create_agent_alias(
            agent_id=agent_id, alias_name=alias_name
        )
        return agent_alias_id, agent_alias_arn, agent_alias_version

    def create_supervisor(
        self,
        project_uuid: str,
        supervisor_name: str,
        supervisor_description: str,
        supervisor_instructions: str
    ):
        external_id, alias_name = self.create_external_supervisor(
            supervisor_name,
            supervisor_description,
            supervisor_instructions,
        )

        self.external_agent_client.wait_agent_status_update(external_id)
        team: Team = self.create_team_object(
            project_uuid=project_uuid,
            external_id=external_id,
            metadata={"supervisor_name": supervisor_name}
        )
        return team

    def create_external_supervisor(
        self,
        supervisor_name: str,
        supervisor_description: str,
        supervisor_instructions: str,
    ) -> Tuple[str, str]:
        return self.external_agent_client.create_supervisor(
            supervisor_name,
            supervisor_description,
            supervisor_instructions,
        )

    def create_agent_version(self, agent_external_id, user):
        print("Creating a new agent version ...")
        agent = Agent.objects.get(external_id=agent_external_id)
        current_version = agent.current_version

        if agent.list_versions.count() == 9:
            oldest_version = agent.list_versions.first()
            self.delete_agent_version(agent_external_id, oldest_version)

        alias_name = f"v{current_version.id+1}"

        agent_alias_id, agent_alias_arn, agent_alias_version = self.external_agent_client.create_agent_alias(
            alias_name=alias_name, agent_id=agent_external_id
        )
        agent_version: AgentVersion = agent.versions.create(
            alias_id=agent_alias_id,
            alias_name=alias_name,
            metadata={
                "agent_alias": agent_alias_arn,
                "agent_alias_version": agent_alias_version,
            },
            created_by=user,
        )
        return agent_version

    def create_skill(
        self,
        agent_external_id: str,
        file_name: str,
        agent_version: str,
        file: bytes,
        function_schema: List[Dict],
        user: User,
    ):
        """
        Creates a new Lambda function for an agent skill and creates its alias.

        Args:
            agent_external_id: The external ID of the agent
            file_name: The name of the Lambda function
            agent_version: The version of the agent
            file: The function code, packaged as bytes in .zip format
            function_schema: The schema defining the function interface
            user: The user creating the skill
        """
        # Create the Lambda function
        lambda_response = run_create_lambda_function(
            agent_external_id=agent_external_id,
            lambda_name=file_name,
            agent_version=agent_version,
            zip_content=file,
            function_schema=function_schema,
        )

        # Create the 'live' alias pointing to $LATEST version
        alias_response = self.create_skill_alias(
            function_name=file_name,
            version='$LATEST',  # Point to latest version
            alias_name='live'
        )

        # Get the agent instance
        agent = Agent.objects.get(external_id=agent_external_id)

        # Extract the original skill name from the file_name (remove the agent_external_id suffix)
        original_skill_name = file_name.rsplit('-', 1)[0]

        # Save skill information to AgentSkills model
        AgentSkills.objects.create(
            display_name=original_skill_name,
            unique_name=file_name,
            agent=agent,
            skill={
                'function_name': file_name,
                'function_arn': lambda_response['FunctionArn'],
                'runtime': 'python3.12',
                'role': lambda_response['Role'],
                'handler': 'lambda_function.lambda_handler',
                'code_size': lambda_response['CodeSize'],
                'description': f"Skill function for agent {agent.display_name}",
                'last_modified': lambda_response['LastModified'],
                'version': lambda_response['Version'],
                'alias_name': 'live',
                'alias_arn': alias_response['AliasArn'],
                'agent_version': agent_version
            },
            created_by=user
        )

    def create_skill_alias(
        self,
        function_name: str,
        version: str,
        alias_name: str = 'live',
        description: str = 'Production alias for the skill'
    ):
        """
        Creates an alias for a Lambda function skill.

        Args:
            function_name: Name of the Lambda function
            version: Version of the function to point to (can be version number or $LATEST)
            alias_name: Name of the alias (defaults to 'live')
            description: Description of the alias
        """
        try:
            response = self.external_agent_client.lambda_client.create_alias(
                FunctionName=function_name,
                Name=alias_name,
                FunctionVersion=version,
                Description=description
            )
            print(f"Created alias {alias_name} for function {function_name}")
            return response
        except self.external_agent_client.lambda_client.exceptions.ResourceConflictException:
            # If alias already exists, update it
            print(f"Alias {alias_name} already exists for function {function_name}, updating...")
            response = self.external_agent_client.lambda_client.update_alias(
                FunctionName=function_name,
                Name=alias_name,
                FunctionVersion=version,
                Description=description
            )
            return response
        except Exception as e:
            print(f"Error creating/updating alias for function {function_name}: {str(e)}")
            raise

    def update_skill(
        self,
        file_name: str,
        agent_external_id: str,
        agent_version: str,
        file: bytes,
        function_schema: List[Dict],
        user: User,
    ):
        """
        Updates the code for an existing Lambda function associated with an agent skill.

        Args:
            file_name: Name of the Lambda function to update
            agent_external_id: External ID of the agent
            agent_version: Version of the agent
            file: Function code to update (bytes in .zip format)
            function_schema: Schema defining the function interface
            user: User updating the skill
        """
        print("----------- STARTING UPDATE LAMBDA FUNCTION ---------")

        # Get the agent and skill instances first
        agent = Agent.objects.get(external_id=agent_external_id)
        skill = AgentSkills.objects.get(unique_name=file_name, agent=agent)

        # Use the stored skill data for the update
        lambda_response = run_update_lambda_function(
            agent_external_id=agent_external_id,
            lambda_name=skill.skill['function_name'],
            lambda_arn=skill.skill['function_arn'],
            agent_version=agent_version,
            zip_content=file,
            function_schema=function_schema,
        )

        print("----------- UPDATED LAMBDA FUNCTION ---------")

        # Update skill information with new data while preserving existing fields
        skill.skill.update({
            'code_size': lambda_response['CodeSize'],
            'last_modified': lambda_response['LastModified'],
            'version': lambda_response['Version'],
            'agent_version': agent_version,
            # Preserve other important fields from the original skill data
            'function_name': skill.skill['function_name'],
            'function_arn': skill.skill['function_arn'],
            'runtime': skill.skill['runtime'],
            'role': skill.skill['role'],
            'handler': skill.skill['handler'],
            'description': skill.skill['description'],
            'alias_name': skill.skill['alias_name'],
            'alias_arn': skill.skill['alias_arn']
        })
        skill.modified_by = user
        skill.save()

        print(f"Updated skill {skill.display_name} for agent {agent.display_name}")

    def create_team_object(self, project_uuid: str, external_id: str, metadata: Dict) -> Team:
        return Team.objects.create(
            project_id=project_uuid,
            external_id=external_id,
            metadata=metadata,
        )

    def get_agent_object(self, **kwargs) -> Agent:
        """
        external_id: str
        uuid: str
        """
        agent = Agent.objects.get(**kwargs)
        return agent

    def get_team_object(self, **kwargs) -> Team:
        return Team.objects.get(**kwargs)

    def invoke_supervisor(self, session_id, supervisor_id, supervisor_alias_id, prompt, content_base_uuid):
        response = self.external_agent_client.invoke_supervisor(
            supervisor_id=supervisor_id,
            supervisor_alias_id=supervisor_alias_id,
            session_id=session_id,
            prompt=prompt,
            content_base_uuid=content_base_uuid,
        )
        return response

    def prepare_agent(self, agent_id: str):
        self.external_agent_client.prepare_agent(agent_id)
        return

    def unassign_agent(self, agent_uuid, project_uuid):
        agent: Agent = self.get_agent_object(uuid=agent_uuid)
        team: Team = self.get_team_object(project__uuid=project_uuid)
        sub_agent_id = ""

        supervisor_id: str = team.external_id
        collaborators = BedrockFileDatabase().bedrock_agent.list_agent_collaborators(
            agentId=supervisor_id,
            agentVersion='DRAFT'
        )
        summaries = collaborators["agentCollaboratorSummaries"]
        for agent_descriptor in summaries:
            if agent.external_id in agent_descriptor["agentDescriptor"]["aliasArn"]:
                sub_agent_id = agent_descriptor["collaboratorId"]

        if sub_agent_id:
            self.external_agent_client.disassociate_sub_agent(
                supervisor_id=supervisor_id,
                supervisor_version='DRAFT',
                sub_agent_id=sub_agent_id,
            )

    def update_agent(self, agent_dto: UpdateAgentDTO, project_uuid: str):

        agent = Agent.objects.filter(display_name=agent_dto.name, project_id=project_uuid).first()

        self.external_agent_client.update_agent(
            agent_dto=agent_dto,
            agent_id=agent.external_id,
        )

        self.prepare_agent(agent.external_id)

        if agent_dto.description:
            agent.description = agent_dto.description

        if agent_dto.foundation_model:
            agent.model = agent_dto.foundation_model

        agent.save()

        return agent

    def validate_agent_dto(
        self,
        agent_dto: AgentDTO,
        user_email: str,
        allowed_users: List[str] = settings.AGENT_CONFIGURATION_ALLOWED_USERS
    ):
        if agent_dto.slug is not None:
            if len(agent_dto.slug) > 128:
                raise AgentNameTooLong

        if agent_dto.instructions is not None:
            if isinstance(agent_dto, UpdateAgentDTO):
                if len(agent_dto.instructions) < 40:
                    raise AgentInstructionsTooShort
            else:
                for instruction in agent_dto.instructions:
                    if len(instruction) < 40:
                        raise AgentInstructionsTooShort

        if agent_dto.guardrails is not None:
            for guardrail in agent_dto.guardrails:
                if len(guardrail) < 40:
                    raise AgentInstructionsTooShort

        if agent_dto.skills is not None:
            for skill in agent_dto.skills:
                if len(skill.get('slug')) > 53:
                    raise SkillNameTooLong

        agent_attributes = agent_dto.prompt_override_configuration or agent_dto.memory_configuration
        if agent_attributes and user_email not in allowed_users:
            raise AgentAttributeNotAllowed

        if hasattr(agent_dto, 'model') and agent_dto.model is not None:
            agents_model: List[str] = settings.AWS_BEDROCK_AGENTS_MODEL_ID
            if not set(agent_dto.model).issubset(agents_model) and user_email not in allowed_users:
                raise AgentAttributeNotAllowed

        return agent_dto

    def update_dict_to_dto(
        self,
        agent_value: dict,
        user_email: str
    ) -> UpdateAgentDTO:

        def format_instructions(instructions: List[str]):
            return "\n".join(instructions)

        all_instructions = agent_value.get("instructions") + agent_value.get("guardrails")
        instructions = format_instructions(all_instructions)

        agent_dto = UpdateAgentDTO(
            name=agent_value.get("name"),
            instructions=instructions,
            guardrails=agent_value.get("guardrails"),
            description=agent_value.get("description"),
            memory_configuration=agent_value.get("memory_configuration"),
            prompt_override_configuration=agent_value.get("prompt_override_configuration"),
            idle_session_ttl_in_seconds=agent_value.get("idle_session_ttl_in_seconds"),
            guardrail_configuration=agent_value.get("guardrail_configuration"),
            model=agent_value.get("model"),
            skills=agent_value.get("skills"),
        )
        validate_agents = self.validate_agent_dto(agent_dto, user_email)
        return validate_agents

    def create_dict_to_dto(
        self,
        agent_value: dict,
        user_email: str
    ) -> AgentDTO:

        agent_dto = AgentDTO(
            slug=slugify(agent_value.get('name')),
            name=agent_value.get("name"),
            description=agent_value.get("description"),
            instructions=agent_value.get("instructions"),
            guardrails=agent_value.get("guardrails"),
            skills=agent_value.get("skills"),
            model=settings.AWS_BEDROCK_AGENTS_MODEL_ID,
            prompt_override_configuration=agent_value.get("prompt_override_configuration"),
            memory_configuration=agent_value.get("memory_configuration"),
            tags=agent_value.get("tags"),
        )
        validate_agents = self.validate_agent_dto(agent_dto, user_email)
        return validate_agents

    def agent_dto_handler(
        self,
        project_uuid: str,
        yaml: dict,
        user_email: str
    ):

        existing_agents_dto = []
        to_create_agents_dto = []
        for agent_key, agent_value in yaml.get("agents", {}).items():

            agent = Agent.objects.filter(
                display_name=agent_value.get("name"),
                project_id=project_uuid
            )

            if agent.exists():
                dto = self.update_dict_to_dto(agent_value=agent_value, user_email=user_email)
                existing_agents_dto.append(dto)
            else:
                dto = self.create_dict_to_dto(agent_value=agent_value, user_email=user_email)
                to_create_agents_dto.append(dto)

        return existing_agents_dto + to_create_agents_dto

    def wait_agent_status_update(self, external_id: str):
        self.agent_for_amazon_bedrock.wait_agent_status_update(external_id)

    def handle_agent_skills(
        self,
        agent: Agent,
        skills: List[Dict],
        files: Dict,
        user: User
    ):
        """
        Handle creation or update of agent skills.

        Args:
            agent: The agent to handle skills for
            skills: List of skill configurations
            files: Dictionary of uploaded files
            user: The user creating the skills
        """
        for skill in skills:
            slug = skill.get('slug')
            skill_file = files[f"{agent.slug}:{slug}"]
            skill_file = skill_file.read()
            skill_parameters = skill.get("parameters")

            if isinstance(skill_parameters, list):
                params = {}
                for param in skill_parameters:
                    params.update(param)
                skill_parameters = params

            lambda_name = f"{slug}-{agent.external_id}"
            function_schema = [
                {
                    "name": skill.get("slug"),
                    "parameters": skill_parameters,
                }
            ]

            # Check if skill exists before deciding to update or create
            try:
                AgentSkills.objects.get(unique_name=lambda_name, agent=agent)
                print(f"Updating existing skill: {lambda_name}")
                self.update_skill(
                    file_name=lambda_name,
                    agent_external_id=agent.metadata["external_id"],
                    agent_version=agent.metadata.get("agentVersion"),
                    file=skill_file,
                    function_schema=function_schema,
                    user=user
                )
            except AgentSkills.DoesNotExist:
                print(f"Creating new skill: {lambda_name}")
                self.create_skill(
                    agent_external_id=agent.metadata["external_id"],
                    file_name=lambda_name,
                    agent_version=agent.metadata.get("agentVersion"),
                    file=skill_file,
                    function_schema=function_schema,
                    user=user
                )

    def create_supervisor_version(self, project_uuid, user):
        project = Project.objects.get(uuid=project_uuid)
        team = project.team
        current_version = team.current_version
        supervisor_name = team.metadata.get("supervisor_name")
        supervisor_id = team.external_id

        # self.bedrock_agent.list_agent_versions(agentId=supervisor_id)
        if team.list_versions.count() == 9:
            oldest_version = team.list_versions.first()
            self.delete_agent_version(team.external_id, oldest_version)

        alias_name = f"{supervisor_name}-multi-agent-{current_version.id+1}"

        supervisor_agent_alias_id, supervisor_agent_alias_arn, supervisor_alias_version = self.external_agent_client.create_agent_alias(
            alias_name=alias_name, agent_id=supervisor_id
        )
        team.versions.create(
            alias_id=supervisor_agent_alias_id,
            alias_name=alias_name,
            metadata={
                "supervisor_alias_arn": supervisor_agent_alias_arn,
                "supervisor_alias_version": supervisor_alias_version,
            },
            created_by=user,
        )

    def delete_agent_version(self, agent_id: str, version):
        try:
            response = self.external_agent_client.bedrock_agent.delete_agent_alias(
                agentId=agent_id,
                agentAliasId=version.alias_id
            )
            print(response)
            version.delete()
            return response
        except Exception:
            raise

    def update_supervisor_collaborator(self, project_uuid: str, agent):
        """Update multi-agent DRAFT to point to updated agent version"""
        team = Team.objects.get(project__uuid=project_uuid)
        response = self.external_agent_client.bedrock_agent.get_agent_collaborator(
            agentId=team.external_id,
            agentVersion=team.current_version.metadata.get("supervisor_alias_version"),
            collaboratorId=team.team_agents.get(agent__external_id=agent.external_id).metadata.get("agent_collaborator_id")
        )
        current_agent_collaborator = response["agentCollaborator"]

        response = self.external_agent_client.bedrock_agent.update_agent_collaborator(
            agentDescriptor={
                'aliasArn': agent.current_version.metadata["agent_alias"]
            },
            agentId=current_agent_collaborator["agentId"],
            agentVersion="DRAFT",
            collaborationInstruction=current_agent_collaborator["collaborationInstruction"],
            collaboratorId=current_agent_collaborator["collaboratorId"],
            collaboratorName=current_agent_collaborator["collaboratorName"],
        )
