import uuid

from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from django.conf import settings
from django.template.defaultfilters import slugify

from nexus.internals.flows import FlowsRESTClient

from nexus.users.models import User
from nexus.agents.models import (
    ActiveAgent,
    Agent,
    AgentSkills,
    ContactField,
    Team,
    AgentVersion,
    AgentSkillVersion
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
    idle_session_ttl_in_seconds: int = 1800
    is_update: bool = False
    update_fields: dict = field(default_factory=dict)
    foundation_model: str = None
    guardrail_configuration: dict = None
    credentials: List[Dict] = None

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}


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
    def __init__(
        self,
        external_agent_client=BedrockFileDatabase,
        flows_client=FlowsRESTClient
    ):
        self.external_agent_client = external_agent_client()
        self.flows_client = flows_client()

    def assign_agent(self, agent_uuid: str, project_uuid: str, created_by):
        agent: Agent = self.get_agent_object(uuid=agent_uuid)
        team: Team = self.get_team_object(project__uuid=project_uuid)

        if str(agent.project.uuid) != project_uuid:
            print("[+ Creating contact fields for agent +]")
            fields = []
            for contact_field in agent.contact_fields.all():
                key = contact_field.key
                value_type = contact_field.value_type
                print(f"Contact field: {key} {value_type}")
                fields.append({
                    "key": key,
                    "value_type": value_type
                })
            self.create_contact_fields(project_uuid, fields, agent=agent)

        sub_agent = BedrockSubAgent(
            display_name=agent.display_name,
            slug=agent.slug,
            external_id=agent.external_id,
            alias_arn=agent.current_version.metadata.get("agent_alias"),
            description=agent.description,
        )

        if team.metadata.get("is_single_agent"):
            self.update_multi_agent(team)

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

        all_instructions = ""
        if agent_dto.instructions:
            all_instructions = agent_dto.instructions
            if agent_dto.guardrails:
                all_instructions = agent_dto.instructions + agent_dto.guardrails

        external_id = self.create_external_agent(
            agent_name=f"{agent_dto.slug}-project-{project_uuid}",
            agent_description=agent_dto.description,
            agent_instructions=format_instructions(all_instructions),
            idle_session_tll_in_seconds=agent_dto.idle_session_ttl_in_seconds,
            memory_configuration=agent_dto.memory_configuration,
            prompt_override_configuration=agent_dto.prompt_override_configuration,
            tags=agent_dto.tags,
            model_id=agent_dto.model[0],
        )
        return external_id

    def create_contact_fields(self, project_uuid: str, fields: List[Dict[str, str]], agent, convert_fields: bool = True):
        types = {
            "string": "text",
            "boolean": "text",
            "array": "text",
            "number": "numeric",
            "integer": "numeric",
            # "state": "state",
            # "ward": "ward",
            # "district": "district",
            # "datetime": "datetime",
        }

        flows_client = FlowsRESTClient()
        flows_contact_fields = flows_client.list_project_contact_fields(project_uuid)
        results = flows_contact_fields.get('results', []) if isinstance(flows_contact_fields, dict) else flows_contact_fields
        existing_keys = set(field.get('key', '') for field in results)

        for contact_field in fields:
            if contact_field.get('key') not in existing_keys:
                if convert_fields:
                    value_type = types.get(contact_field.get('value_type'))
                else:
                    value_type = contact_field.get('value_type')
                    
                print(f"Creating contact field: {contact_field.get('key')} {value_type}")
                ContactField.objects.create(
                    project_id=project_uuid,
                    key=contact_field.get('key'),
                    value_type=value_type,
                    agent=agent,
                )
                flows_client.create_project_contact_field(
                    project_uuid=project_uuid,
                    key=contact_field.get('key'),
                    value_type=value_type
                )

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

    def update_agent_to_supervisor(self, agent_id: str, to_supervisor: bool = True):
        self.external_agent_client.bedrock_agent_to_supervisor(agent_id, to_supervisor)
        self.external_agent_client.wait_agent_status_update(agent_id)

    def create_supervisor(
        self,
        project_uuid: str,
        supervisor_name: str,
        supervisor_description: str,
        supervisor_instructions: str,
        is_single_agent: bool,
    ):
        external_id, alias_name = self.create_external_supervisor(
            supervisor_name,
            supervisor_description,
            supervisor_instructions,
            is_single_agent
        )

        self.external_agent_client.wait_agent_status_update(external_id)
        team: Team = self.create_team_object(
            project_uuid=project_uuid,
            external_id=external_id,
            metadata={
                "supervisor_name": supervisor_name,
                "is_single_agent": is_single_agent,
            }
        )
        self.prepare_agent(team.external_id)
        return team

    def create_external_supervisor(
        self,
        supervisor_name: str,
        supervisor_description: str,
        supervisor_instructions: str,
        is_single_agent: bool,
    ) -> Tuple[str, str]:
        return self.external_agent_client.create_supervisor(
            supervisor_name,
            supervisor_description,
            supervisor_instructions,
            is_single_agent
        )

    def create_agent_version(self, agent_external_id, user, agent, team):
        print("Creating a new agent version ...")

        if agent.list_versions.count() >= 9:
            oldest_version = agent.list_versions.first()
            self.delete_agent_version(agent_external_id, oldest_version, team, user)

        random_uuid = str(uuid.uuid4())
        alias_name = f"version-{random_uuid}"

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
        agent: Agent,
        skill_handler: str
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
            agent=agent,
            skill_handler=skill_handler
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
                'agent_version': agent_version,
                'function_schema': function_schema,
                'skill_handler': skill_handler
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

    def delete_agent(self, agent_external_id: str):
        self.external_agent_client.delete_agent(agent_external_id)

    def update_skill(
        self,
        file_name: str,
        agent_external_id: str,
        agent_version: str,
        file: bytes,
        function_schema: List[Dict],
        user: User,
        skill_handler: str
    ):
        """
        Updates the code for an existing Lambda function associated with an agent skill.
        """
        print("----------- STARTING UPDATE LAMBDA FUNCTION ---------")

        # Get the agent and skill instances first
        agent = Agent.objects.get(external_id=agent_external_id)
        skill_object = AgentSkills.objects.get(unique_name=file_name, agent=agent)

        # Check if any parameter in the function schema has contact_field=True
        if function_schema and function_schema[0].get('parameters'):
            parameters = function_schema[0]['parameters']
            has_contact_field = any(
                isinstance(param_data, dict) and param_data.get('contact_field') is True
                for param_data in parameters.values()
            )
            if has_contact_field:
                self.contact_field_handler(skill_object)

        # Store current version data before update
        AgentSkillVersion.objects.create(
            agent_skill=skill_object,
            metadata={
                'function_name': skill_object.skill['function_name'],
                'function_arn': skill_object.skill['function_arn'],
                'runtime': skill_object.skill['runtime'],
                'role': skill_object.skill['role'],
                'handler': skill_object.skill['handler'],
                'code_size': skill_object.skill['code_size'],
                'description': skill_object.skill['description'],
                'version': skill_object.skill['version'],
                'alias_name': skill_object.skill['alias_name'],
                'alias_arn': skill_object.skill['alias_arn'],
                'agent_version': skill_object.skill['agent_version'],
                'function_schema': skill_object.skill['function_schema'],
                'lambda_version': skill_object.skill.get('lambda_version', '$LATEST'),
                'skill_handler': skill_object.skill['skill_handler']
            },
            created_by=user
        )

        # Use the stored skill data for the update
        lambda_response = run_update_lambda_function(
            agent_external_id=agent_external_id,
            lambda_name=skill_object.skill['function_name'],
            lambda_arn=skill_object.skill['function_arn'],
            agent_version=agent_version,
            zip_content=file,
            function_schema=function_schema,
        )

        # Get the action group for the agent
        action_group = self.external_agent_client.get_agent_action_group(
            agent_id=agent.external_id,
            action_group_id=agent.metadata.get('action_group').get('actionGroupId'),
            agent_version=agent.current_version.metadata.get("agent_alias_version")
        )

        # Update the action group
        self.external_agent_client.update_agent_action_group(
            agent_external_id=agent.external_id,
            action_group_name=action_group['agentActionGroup']['actionGroupName'],
            lambda_arn=lambda_response['FunctionArn'],
            agent_version=agent.current_version.metadata.get("agent_alias_version"),
            action_group_id=action_group['agentActionGroup']['actionGroupId'],
            function_schema=function_schema
        )

        print("----------- UPDATED LAMBDA FUNCTION ---------")

        # Update skill information with new data while preserving existing fields
        skill_object.skill.update({
            'code_size': lambda_response['CodeSize'],
            'last_modified': lambda_response['LastModified'],
            'version': lambda_response['Version'],
            'agent_version': agent_version,
            'lambda_version': lambda_response['Version'],  # Store Lambda version number
            # Preserve other important fields from the original skill data
            'function_name': skill_object.skill['function_name'],
            'function_arn': skill_object.skill['function_arn'],
            'runtime': skill_object.skill['runtime'],
            'role': skill_object.skill['role'],
            'handler': skill_object.skill['handler'],
            'description': skill_object.skill['description'],
            'alias_name': skill_object.skill['alias_name'],
            'alias_arn': skill_object.skill['alias_arn']
        })
        skill_object.modified_by = user
        skill_object.save()

        print(f"Updated skill {skill_object.display_name} for agent {agent.display_name}")

        warnings = []
        if skill_object.skill['skill_handler'] != skill_handler:
            warnings.append(f"Skill handler changed from {skill_object.skill['handler']} to {skill_handler}")

        return warnings

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

    def invoke_supervisor_stream(self, session_id, supervisor_id, supervisor_alias_id, content_base, message):
        for chunk in self.external_agent_client.invoke_supervisor_stream(
            supervisor_id=supervisor_id,
            supervisor_alias_id=supervisor_alias_id,
            session_id=session_id,
            content_base=content_base,
            message=message
        ):
            yield chunk

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
            active_agent = team.team_agents.get(agent=agent)
            active_agent.delete()

        if not team.team_agents.exists():
            self.update_multi_agent(team, multi_agent=False)

    def update_agent(self, agent_dto: AgentDTO, project_uuid: str):
        """Update an existing agent with new data"""
        agent = Agent.objects.filter(display_name=agent_dto.name, project_id=project_uuid).first()

        # Update agent in Bedrock
        self.external_agent_client.update_agent(
            agent_dto=agent_dto,  # Use the dict method to get valid fields
            agent_id=agent.external_id,
        )

        # Update local agent model with changed fields
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
        """Validate the AgentDTO fields"""
        if agent_dto.slug is not None:
            if len(agent_dto.slug) > 128:
                raise AgentNameTooLong

        all_instructions = agent_dto.instructions + agent_dto.guardrails
        if all_instructions:
            for instruction in all_instructions:
                if len(instruction) < 40:
                    raise AgentInstructionsTooShort

        if agent_dto.skills:
            for skill in agent_dto.skills:
                if len(skill.get('slug')) > 53:
                    raise SkillNameTooLong

        agent_attributes = agent_dto.prompt_override_configuration or agent_dto.memory_configuration
        if agent_attributes and user_email not in allowed_users:
            raise AgentAttributeNotAllowed

        if agent_dto.model:
            agents_model: List[str] = settings.AWS_BEDROCK_AGENTS_MODEL_ID
            if not set(agent_dto.model).issubset(agents_model) and user_email not in allowed_users:
                raise AgentAttributeNotAllowed

        return agent_dto

    def update_dict_to_dto(
        self,
        agent_value: dict,
        user_email: str
    ) -> AgentDTO:
        """Convert update dictionary to AgentDTO"""
        agent_dto = AgentDTO(
            slug=slugify(agent_value.get('name')),
            name=agent_value.get("name"),
            description=agent_value.get("description"),
            instructions=agent_value.get("instructions", []),
            guardrails=agent_value.get("guardrails", []),
            skills=agent_value.get("skills", []),
            model=agent_value.get("model"),
            prompt_override_configuration=agent_value.get("prompt_override_configuration"),
            memory_configuration=agent_value.get("memory_configuration"),
            idle_session_ttl_in_seconds=agent_value.get("idle_session_ttl_in_seconds"),
            guardrail_configuration=agent_value.get("guardrail_configuration"),
            foundation_model=agent_value.get("foundation_model"),
            is_update=True  # Mark as update
        )
        validate_agents = self.validate_agent_dto(agent_dto, user_email)
        return validate_agents

    def create_dict_to_dto(
        self,
        agent_value: dict,
        user_email: str
    ) -> AgentDTO:
        """Convert dictionary to AgentDTO for creation or update"""
        agent_dto = AgentDTO(
            slug=slugify(agent_value.get('name')),
            name=agent_value.get("name"),
            description=agent_value.get("description"),
            instructions=agent_value.get("instructions", []),
            guardrails=agent_value.get("guardrails", []),
            skills=agent_value.get("skills", []),
            model=settings.AWS_BEDROCK_AGENTS_MODEL_ID,
            prompt_override_configuration=agent_value.get("prompt_override_configuration"),
            memory_configuration=agent_value.get("memory_configuration"),
            tags=agent_value.get("tags"),
            idle_session_ttl_in_seconds=agent_value.get("idle_session_ttl_in_seconds", 1800),
            foundation_model=agent_value.get("foundation_model"),
            guardrail_configuration=agent_value.get("guardrail_configuration"),
            credentials=agent_value.get("credentials"),
        )
        validate_agents = self.validate_agent_dto(agent_dto, user_email)
        return validate_agents

    def agent_dto_handler(
        self,
        project_uuid: str,
        yaml: dict,
        user_email: str
    ):
        """
        Handles both creation and updates of agents using the same DTO structure.
        Compares existing agent data with incoming data to determine what needs to be updated.
        """
        agents_dto = []
        for agent_key, agent_value in yaml.get("agents", {}).items():
            agent = Agent.objects.filter(
                display_name=agent_value.get("name"),
                project_id=project_uuid
            ).first()

            # Convert incoming data to DTO
            agent_dto = self.create_dict_to_dto(
                agent_value=agent_value,
                user_email=user_email
            )

            if agent:
                # If agent exists, compare and mark fields that need updating
                agent_dto.is_update = True
                agent_dto.update_fields = self._get_update_fields(agent, agent_dto)

                # Compare skills and mark which ones need to be updated or created
                if agent_dto.skills:
                    agent_dto.skills = self._process_skills_update(agent, agent_dto.skills)

            agents_dto.append(agent_dto)

        return agents_dto

    def _get_update_fields(self, existing_agent: Agent, new_dto: AgentDTO) -> dict:
        """
        Compares existing agent with new DTO to determine which fields need updating.
        """
        updates = {}

        if existing_agent.description != new_dto.description:
            updates['description'] = new_dto.description

        if new_dto.instructions:
            current_instructions = "\n".join(existing_agent.metadata.get('instructions', []))
            new_instructions = "\n".join(new_dto.instructions)
            if current_instructions != new_instructions:
                updates['instructions'] = new_dto.instructions

        if new_dto.guardrails:
            current_guardrails = "\n".join(existing_agent.metadata.get('guardrails', []))
            new_guardrails = "\n".join(new_dto.guardrails)
            if current_guardrails != new_guardrails:
                updates['guardrails'] = new_dto.guardrails

        if new_dto.model and existing_agent.model != new_dto.model:
            updates['model'] = new_dto.model

        return updates

    def _process_skills_update(self, existing_agent: Agent, new_skills: List[Dict]) -> List[Dict]:
        """
        Processes skills to determine which need to be updated or created.
        Adds update/create flag to each skill.
        """
        processed_skills = []

        for skill in new_skills:
            skill_name = f"{skill['slug']}-{existing_agent.external_id}"
            existing_skill = AgentSkills.objects.filter(
                unique_name=skill_name,
                agent=existing_agent
            ).first()

            if existing_skill:
                # Mark skill for update and include existing data
                skill['is_update'] = True
                skill['existing_data'] = {
                    'function_name': existing_skill.skill['function_name'],
                    'function_arn': existing_skill.skill['function_arn'],
                    'runtime': existing_skill.skill['runtime'],
                    'handler': existing_skill.skill['handler'],
                    'role': existing_skill.skill['role']
                }
            else:
                # Mark as new skill
                skill['is_update'] = False

            processed_skills.append(skill)

        return processed_skills

    def wait_agent_status_update(self, external_id: str):
        self.external_agent_client.wait_agent_status_update(external_id)

    def handle_agent_skills(
        self,
        agent: Agent,
        skills: List[Dict],
        files: Dict,
        user: User,
        project_uuid: str
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
            skill_handler = skill.get("source").get("entrypoint")
            slug = skill.get('slug')
            skill_file = files[f"{agent.slug}:{slug}"]
            skill_file = skill_file.read()
            skill_parameters = skill.get("parameters")

            fields = []

            if isinstance(skill_parameters, list):
                params = {}
                for param in skill_parameters:
                    for key, value in param.items():
                        if value.get("contact_field"):
                            fields.append({
                                "key": key,
                                "value_type": value.get("type")
                            })
                        param[key].pop("contact_field", None)
                    params.update(param)
                skill_parameters = params

            self.create_contact_fields(project_uuid, fields, convert_fields=False, agent=agent)

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
                warnings = self.update_skill(
                    file_name=lambda_name,
                    agent_external_id=agent.external_id,
                    agent_version=agent.current_version.metadata.get("agent_alias_version"),
                    file=skill_file,
                    function_schema=function_schema,
                    user=user,
                    skill_handler=skill_handler
                )
                return warnings
            except AgentSkills.DoesNotExist:
                print(f"[+ Creating new skill: {lambda_name} +]")
                self.create_skill(
                    agent_external_id=agent.external_id,
                    file_name=lambda_name,
                    agent_version=agent.current_version.metadata.get("agent_alias_version"),
                    file=skill_file,
                    function_schema=function_schema,
                    user=user,
                    agent=agent,
                    skill_handler=skill_handler
                )

    def create_supervisor_version(self, project_uuid, user):
        project = Project.objects.get(uuid=project_uuid)
        team = project.team
        current_version = team.current_version
        supervisor_name = team.metadata.get("supervisor_name")
        supervisor_id = team.external_id

        if current_version:
            self.delete_supervisor_version(team.external_id, current_version)

        alias_name = f"{supervisor_name}-multi-agent"

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

    def delete_supervisor_version(self, agent_id: str, version):
        try:
            response = self.external_agent_client.bedrock_agent.delete_agent_alias(
                agentId=agent_id,
                agentAliasId=version.alias_id
            )
            self.external_agent_client.bedrock_agent.delete_agent_version(
                agentId=agent_id,
                agentVersion=version.metadata["supervisor_alias_version"]
            )
            print(response)
            version.delete()
            return response
        except Exception:
            raise

    def delete_agent_version(self, agent_id: str, version, team, user):
        try:
            project = team.project
            project_uuid = str(project.uuid)
            reasign_agent = False

            if version.alias_id != "DRAFT":
                agent = project.agent_set.get(external_id=agent_id)
                active_agent_qs = team.team_agents.filter(agent=agent)

                if active_agent_qs.exists():
                    reasign_agent = True
                    self.unassign_agent(str(agent.uuid), project_uuid)
                    self.delete_supervisor_version(team.external_id, team.current_version)
                    self.prepare_agent(agent_id)
                    self.prepare_agent(team.external_id)
                    self.external_agent_client.bedrock_agent.delete_agent_alias(
                        agentId=agent_id,
                        agentAliasId=version.alias_id
                    )
                if reasign_agent:
                    self.assign_agent(str(agent.uuid), project_uuid, user)
                    self.create_supervisor_version(project_uuid, user)

            version.delete()
            return
        except Exception:
            raise

    # TODO: Make it assync
    def contact_field_handler(self, skill_object: AgentSkills):
        """
        Handler for skills that have contact field functionality.
        Checks parameters for contact_field flag and creates corresponding contact fields.
        """
        parameters = skill_object.skill['function_schema'][0]['parameters']

        contact_field_params = []
        for param_key, param_data in parameters.items():
            if isinstance(param_data, dict) and param_data.get('contact_field') is True:
                contact_field_params.append({
                    'key': param_key,  # Use the parameter key as the contact field key
                    'value_type': param_data.get('type', 'text').lower()  # Convert type to value_type
                })

        if contact_field_params:
            flows_contact_fields = self.flows_client.list_project_contact_fields(
                str(skill_object.agent.project.uuid)
            )

            # Handle both list and dict responses
            results = flows_contact_fields.get('results', []) if isinstance(flows_contact_fields, dict) else flows_contact_fields
            existing_keys = set(field.get('key', '') for field in results)

            for param in contact_field_params:
                if param['key'] not in existing_keys:
                    self.flows_client.create_project_contact_field(
                        project_uuid=str(skill_object.agent.project.uuid),
                        key=param['key'],
                        value_type=param['value_type']
                    )

        return True

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
            collaborationInstruction=agent.description,
            collaboratorId=current_agent_collaborator["collaboratorId"],
            collaboratorName=current_agent_collaborator["collaboratorName"],
        )

    def update_multi_agent(self, team: Team, multi_agent: bool = True):
        # TODO: organize code ("multi_agent" and "is_single_agent")
        self.external_agent_client.bedrock_agent_to_supervisor(team.external_id, multi_agent)
        team.metadata["is_single_agent"] = not multi_agent
        team.save(update_fields=["metadata"])
        return
