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
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
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
class InlineAgentDTO:
    """Data transfer object for inline agent configuration."""
    session_id: str
    instruction: str
    input_text: str
    foundation_model: str = None
    action_groups: List[Dict] = None
    knowledge_bases: List[Dict] = None
    guardrail_configuration: Dict = None
    enable_trace: bool = True
    idle_session_ttl_in_seconds: int = 1800
    end_session: bool = False
    session_state: Dict = None
    credentials: Dict = None
    content_base_uuid: str = None

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

    def invoke_inline_agent(self, inline_agent_dto: InlineAgentDTO, message=None):
        """
        Invoke an inline agent with the provided configuration.
        
        Args:
            inline_agent_dto: Configuration for the inline agent
            message: Optional message object to extract additional context
        """
        agent_params = inline_agent_dto.dict()
        
        # Remove content_base_uuid since it's not a parameter for invoke_inline_agent
        content_base_uuid = agent_params.pop('content_base_uuid', None)
        
        return self.external_agent_client.invoke_inline_agent(**agent_params)

    def invoke_inline_agent_stream(self, 
                                  session_id: str, 
                                  input_text: str, 
                                  instruction: str, 
                                  content_base, 
                                  foundation_model: str = None,
                                  action_groups: List[Dict] = None,
                                  message = None):
        """
        Invoke an inline agent with streaming response.
        """
        for chunk in self.external_agent_client.invoke_inline_agent_stream(
            session_id=session_id,
            input_text=input_text,
            instruction=instruction,
            content_base=content_base,
            foundation_model=foundation_model,
            action_groups=action_groups,
            message=message,
            enable_trace=True
        ):
            yield chunk

    def create_skill(
        self,
        file_name: str,
        file: bytes,
        function_schema: List[Dict],
        user: User,
        agent: Agent,
        skill_handler: str
    ):
        """
        Creates a new Lambda function for an agent skill and creates its alias.

        Args:
            file_name: The name of the Lambda function
            file: The function code, packaged as bytes in .zip format
            function_schema: The schema defining the function interface
            user: The user creating the skill
            agent: The agent to associate the skill with
            skill_handler: The Lambda handler
        """
        # Create the Lambda function
        lambda_response = self.external_agent_client.create_lambda_function(
            lambda_name=file_name,
            source_code_file=file,
            skill_handler=skill_handler
        )

        # Allow Bedrock to invoke the Lambda function
        self.external_agent_client._allow_agent_lambda(lambda_name)

        # Save skill information to AgentSkills model
        skill = AgentSkills.objects.create(
            display_name=file_name.rsplit('-', 1)[0],  # Extract the original skill name
            unique_name=file_name,
            agent=agent,
            skill={
                'function_name': file_name,
                'function_arn': lambda_response['FunctionArn'],
                'runtime': 'python3.12',
                'role': lambda_response['Role'],
                'handler': skill_handler,
                'code_size': lambda_response['CodeSize'],
                'description': f"Skill function for agent {agent.display_name}",
                'last_modified': lambda_response['LastModified'],
                'version': lambda_response['Version'],
                'alias_name': 'live',
                'alias_arn': lambda_response.get('FunctionArn'),
                'function_schema': function_schema,
                'skill_handler': skill_handler
            },
            created_by=user
        )
        
        return skill

    def update_skill(
        self,
        file_name: str,
        file: bytes,
        function_schema: List[Dict],
        user: User,
        agent: Agent,
        skill_handler: str
    ):
        """
        Updates the code for an existing Lambda function associated with an agent skill.
        """
        print("----------- STARTING UPDATE LAMBDA FUNCTION ---------")

        # Get the skill instance
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
                'function_schema': skill_object.skill['function_schema'],
                'lambda_version': skill_object.skill.get('lambda_version', '$LATEST'),
                'skill_handler': skill_object.skill['skill_handler']
            },
            created_by=user
        )

        # Update the Lambda function
        lambda_response = self.external_agent_client.update_lambda_function(
            lambda_name=skill_object.skill['function_name'],
            zip_content=file,
        )

        print("----------- UPDATED LAMBDA FUNCTION ---------")

        # Update skill information with new data while preserving existing fields
        skill_object.skill.update({
            'code_size': lambda_response['CodeSize'],
            'last_modified': lambda_response['LastModified'],
            'version': lambda_response['Version'],
            'lambda_version': lambda_response['Version'],  # Store Lambda version number
            'function_schema': function_schema
        })
        skill_object.modified_by = user
        skill_object.save()

        print(f"Updated skill {skill_object.display_name} for agent {agent.display_name}")

        warnings = []
        if skill_object.skill['skill_handler'] != skill_handler:
            warnings.append(f"Skill handler changed from {skill_object.skill['handler']} to {skill_handler}")

        return warnings

    def create_team_object(self, project_uuid: str, metadata: Dict) -> Team:
        """Create a team object for tracking agent groups."""
        return Team.objects.create(
            project_id=project_uuid,
            metadata=metadata,
        )

    def get_agent_object(self, **kwargs) -> Agent:
        """Get an agent object by UUID or other identifiers."""
        agent = Agent.objects.get(**kwargs)
        return agent

    def get_team_object(self, **kwargs) -> Team:
        """Get a team object by project or other identifiers."""
        return Team.objects.get(**kwargs)

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

    def validate_inline_agent_dto(self, inline_agent_dto: InlineAgentDTO):
        """Validate the InlineAgentDTO fields."""
        # Basic validation to ensure required fields are present
        if not inline_agent_dto.session_id:
            raise ValueError("Session ID is required for inline agent")
            
        if not inline_agent_dto.instruction:
            raise ValueError("Instruction is required for inline agent")
            
        return inline_agent_dto

    def create_dict_to_inline_dto(self, agent_data: dict) -> InlineAgentDTO:
        """Convert a dictionary to an InlineAgentDTO."""
        # Extract instruction text from instructions list if needed
        instruction = agent_data.get("instruction", "")
        if not instruction and agent_data.get("instructions"):
            instruction = "\n".join(agent_data.get("instructions"))
            
        # Create DTO
        inline_dto = InlineAgentDTO(
            session_id=agent_data.get("session_id"),
            instruction=instruction,
            input_text=agent_data.get("input_text", ""),
            foundation_model=agent_data.get("foundation_model"),
            action_groups=agent_data.get("action_groups"),
            knowledge_bases=agent_data.get("knowledge_bases"),
            guardrail_configuration=agent_data.get("guardrail_configuration"),
            enable_trace=agent_data.get("enable_trace", True),
            idle_session_ttl_in_seconds=agent_data.get("idle_session_ttl_in_seconds", 1800),
            end_session=agent_data.get("end_session", False),
            session_state=agent_data.get("session_state"),
            credentials=agent_data.get("credentials"),
            content_base_uuid=agent_data.get("content_base_uuid")
        )
        
        return self.validate_inline_agent_dto(inline_dto)

    def handle_agent_skills(
        self,
        agent: Agent,
        skills: List[Dict],
        files: Dict,
        user: User,
        project_uuid: str
    ):
        """
        Handle creation or update of agent skills that will be used with inline agents.
        """
        skill_results = []
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

            self.create_contact_fields(project_uuid, fields, agent=agent)

            lambda_name = f"{slug}-{uuid.uuid4()}"  # Use UUID instead of agent external ID
            function_schema = [
                {
                    "name": skill.get("slug"),
                    "parameters": skill_parameters,
                }
            ]

            # Check if skill exists
            existing_skill = AgentSkills.objects.filter(display_name=slug, agent=agent).first()
            
            if existing_skill:
                print(f"Updating existing skill: {lambda_name}")
                warnings = self.update_skill(
                    file_name=existing_skill.unique_name,
                    file=skill_file,
                    function_schema=function_schema,
                    user=user,
                    agent=agent,
                    skill_handler=skill_handler
                )
                skill_results.append({"name": slug, "status": "updated", "warnings": warnings})
            else:
                print(f"[+ Creating new skill: {lambda_name} +]")
                new_skill = self.create_skill(
                    file_name=lambda_name,
                    file=skill_file,
                    function_schema=function_schema,
                    user=user,
                    agent=agent,
                    skill_handler=skill_handler
                )
                skill_results.append({"name": slug, "status": "created", "skill_id": str(new_skill.uuid)})
                
        return skill_results

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
        
