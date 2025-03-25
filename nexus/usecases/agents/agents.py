import uuid
import json

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
from nexus.agents.models import AgentMessage


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
        """
        Assigns an agent to a project. With inline agents, we just track the relationship
        but don't need to create agent aliases or versions.
        """
        agent: Agent = self.get_agent_object(uuid=agent_uuid)
        team: Team = self.get_team_object(project__uuid=project_uuid)

        if str(agent.project.uuid) != project_uuid:
            print("[+ Creating contact fields for agent +]")
            fields = []
            for contact_field in agent.contact_fields.distinct("key"):
                key = contact_field.key
                value_type = contact_field.value_type
                print(f"Contact field: {key} {value_type}")
                fields.append({
                    "key": key,
                    "value_type": value_type
                })
            self.create_contact_fields(project_uuid, fields, agent=agent, convert_fields=False)

        # Create or get active agent
        active_agent, created = ActiveAgent.objects.get_or_create(
            agent=agent,
            team=team,
            is_official=agent.is_official,
            created_by=created_by,
            metadata={}
        )
        return active_agent

    def create_agent(self, user: User, agent_dto: AgentDTO, project_uuid: str, alias_name: str = "v1"):
        """
        For backward compatibility, creates and registers a new agent in the database.
        The actual agent creation happens at runtime with inline agents.
        """
        print("----------- STARTING CREATE AGENT ---------")
        
        # Generate a unique ID for the agent that will be used in the database
        external_id = f"inline-agent-{uuid.uuid4()}"
        
        # Instead of creating an actual agent in AWS, just return the ID
        # The actual agent configuration will be used at runtime
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
        """
        For backward compatibility. With inline agents, we just create a unique ID.
        The actual agent configuration will be provided at invocation time.
        """
        return f"inline-agent-{uuid.uuid4()}"

    def create_external_agent_alias(self, agent_id: str, alias_name: str) -> Tuple[str, str, str]:
        """
        For backward compatibility. With inline agents, aliases aren't needed.
        Returns dummy values to maintain API compatibility.
        """
        alias_id = f"inline-alias-{uuid.uuid4()}"
        alias_arn = f"arn:aws:bedrock:{settings.AWS_BEDROCK_REGION_NAME}:{self.external_agent_client.account_id}:agent-alias/{alias_id}"
        alias_version = "v1"
        return alias_id, alias_arn, alias_version

    def create_supervisor(
        self,
        project_uuid: str,
        supervisor_name: str,
        supervisor_description: str,
        supervisor_instructions: str,
        is_single_agent: bool,
    ):
        """
        For backward compatibility. With inline agents, supervisors are configured at runtime.
        """
        external_id = f"inline-supervisor-{uuid.uuid4()}"
        team: Team = self.create_team_object(
            project_uuid=project_uuid,
            external_id=external_id,
            metadata={
                "supervisor_name": supervisor_name,
                "is_single_agent": is_single_agent,
                "supervisor_description": supervisor_description,
                "supervisor_instructions": supervisor_instructions,
            }
        )
        return team

    def create_external_supervisor(
        self,
        supervisor_name: str,
        supervisor_description: str,
        supervisor_instructions: str,
        is_single_agent: bool,
    ) -> Tuple[str, str]:
        """
        For backward compatibility. With inline agents, supervisors are configured at runtime.
        """
        return f"inline-supervisor-{uuid.uuid4()}", supervisor_name

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
        This is still needed with inline agents.
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

    def invoke_agent_stream(self, session_id, agent, content_base, message):
        """
        Invokes an inline agent with streaming response.
        """
        # Get agent configuration from database
        agent_instructions = self._get_agent_instructions(agent)
        
        # Format instructions for inline agent
        formatted_instructions = self._format_agent_instructions(agent_instructions)
        
        # Invoke inline agent with streaming
        for chunk in self.external_agent_client.invoke_inline_agent_stream(
            session_id=session_id,
            input_text=message.text,
            instruction=formatted_instructions,
            content_base=content_base,
            message=message
        ):
            yield chunk

    def _get_agent_instructions(self, agent):
        """Gets agent instructions from the agent record"""
        # Try to get instructions from agent metadata
        instructions = agent.metadata.get('instructions', [])
        guardrails = agent.metadata.get('guardrails', [])
        
        # Combine instructions and guardrails
        all_instructions = instructions + guardrails
        
        # Add agent role/personality/goal if available
        if hasattr(agent, 'role') and agent.role:
            all_instructions.append(f"You are a {agent.role}.")
        if hasattr(agent, 'personality') and agent.personality:
            all_instructions.append(f"Your personality is {agent.personality}.")
        if hasattr(agent, 'goal') and agent.goal:
            all_instructions.append(f"Your goal is to {agent.goal}.")
            
        return all_instructions

    def _format_agent_instructions(self, instructions):
        """Format instructions for the inline agent"""
        if not instructions:
            return "You are a helpful assistant."
            
        return "\n".join(instructions)

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

    def contact_field_handler(self, skill_object: AgentSkillVersion):
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

    def get_agent_message_by_id(self, agent_message_id: str):
        return AgentMessage.objects.get(id=agent_message_id)

    def list_last_logs(
        self,
        log_id: int,
        message_count: int = 5,
    ):
        log = AgentMessage.objects.get(id=log_id)
        project = log.project
        source = log.source
        contact_urn = log.contact_urn
        created_at = log.created_at

        logs = AgentMessage.objects.filter(
            project=project,
            source=source,
            contact_urn=contact_urn,
            session_id=log.session_id,
            created_at__lt=created_at
        ).order_by("-created_at")[:message_count]

        logs = list(logs)[::-1]

        return logs

    def get_traces(self, project_uuid: str, log_id: str):
        log = AgentMessage.objects.get(id=log_id)
        key = f"traces/{project_uuid}/{log.uuid}.jsonl"
        traces_data = BedrockFileDatabase().get_trace_file(key)
        if traces_data:
            traces = [json.loads(line) for line in traces_data.splitlines() if line]
            return traces
        return []
        
