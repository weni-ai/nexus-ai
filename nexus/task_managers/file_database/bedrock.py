import uuid
import json
import time
from io import BytesIO

from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    List,
    Tuple,
)
from os.path import basename

import boto3
import pendulum
from django.conf import settings
from django.template.defaultfilters import slugify

from nexus.task_managers.file_database.file_database import FileDataBase, FileResponseDTO
from nexus.agents.src.utils.bedrock_agent_helper import AgentsForAmazonBedrock

from nexus.agents.models import Agent


@dataclass
class BedrockSubAgent:
    display_name: str
    slug: str
    external_id: str
    alias_arn: str


class BedrockFileDatabase(FileDataBase):
    def __init__(
        self,
        agent_foundation_model: List = settings.AWS_BEDROCK_AGENTS_MODEL_ID,
        supervisor_foundation_model: List = settings.AWS_BEDROCK_SUPERVISOR_MODEL_ID,
    ) -> None:
        self.data_source_id = settings.AWS_BEDROCK_DATASOURCE_ID
        self.knowledge_base_id = settings.AWS_BEDROCK_KNOWLEDGE_BASE_ID
        self.region_name = settings.AWS_BEDROCK_REGION_NAME
        self.bucket_name = settings.AWS_BEDROCK_BUCKET_NAME
        self.model_id = settings.AWS_BEDROCK_MODEL_ID

        self.agent_for_amazon_bedrock = AgentsForAmazonBedrock()
        # self.agent_for_amazon_bedrock = ...  #  TODO: add AgentsForAmazonBedrock lib
        self.s3_client = self.__get_s3_client()
        self.bedrock_agent = self.__get_bedrock_agent()
        self.bedrock_agent_runtime = self.__get_bedrock_agent_runtime()
        self.bedrock_runtime = self.__get_bedrock_runtime()
        self.lambda_client = self.__get_lambda_client()

        self.agent_foundation_model = agent_foundation_model
        self.supervisor_foundation_model = supervisor_foundation_model

    def invoke_model(self, prompt: str, config_data: Dict):
        data = {
            "top_p": config_data.get("top_p"),
            "top_k": int(config_data.get("top_k")),
            "stop": config_data.get("stop"),
            "temperature": config_data.get("temperature"),
            "prompt": prompt
        }

        payload = json.dumps(data)
        response = self.bedrock_runtime.invoke_model(
            body=payload,
            contentType='application/json',
            accept='application/json',
            modelId=self.model_id,
            trace='ENABLED'
        )
        return response

    def update_agent(
        self,
        agent_id: str,
        agent_dto,
    ):
        bedrock_agent = self.get_agent(agent_id)
        _agent_details = bedrock_agent.get("agent")

        updated_fields = []
        required_fields = ["agentId", "agentName", "agentResourceRoleArn", "foundationModel"]

        if agent_dto.instructions:
            all_instructions = agent_dto.instructions
            if agent_dto.guardrails:
                all_instructions = agent_dto.instructions + agent_dto.guardrails
            instructions = "\n".join(all_instructions)
            _agent_details["instruction"] = instructions
            updated_fields.append("instruction")

        if agent_dto.description:
            _agent_details["description"] = agent_dto.description
            updated_fields.append("description")

        if agent_dto.memory_configuration:
            _agent_details["memoryConfiguration"] = agent_dto.memory_configuration
            updated_fields.append("memoryConfiguration")

        if agent_dto.prompt_override_configuration:
            _agent_details["promptOverrideConfiguration"] = agent_dto.prompt_override_configuration
            updated_fields.append("promptOverrideConfiguration")

        if agent_dto.idle_session_ttl_in_seconds:
            _agent_details["idleSessionTTLInSeconds"] = agent_dto.idle_session_ttl_in_seconds
            updated_fields.append("idleSessionTTLInSeconds")

        if agent_dto.guardrail_configuration:
            _agent_details["guardrailConfiguration"] = agent_dto.guardrail_configuration
            updated_fields.append("guardrailConfiguration")

        if agent_dto.foundation_model:
            _agent_details["foundationModel"] = agent_dto.foundation_model
            updated_fields.append("foundationModel")

        keys_to_remove = [
            key for key in _agent_details.keys()
            if key not in updated_fields and key not in required_fields
        ]

        for key in keys_to_remove:
            del _agent_details[key]

        _update_agent_response = self.bedrock_agent.update_agent(
            **_agent_details
        )

        time.sleep(3)

        return _update_agent_response

    def add_metadata_json_file(self, filename: str, content_base_uuid: str, file_uuid: str):
        print("[+ BEDROCK: Adding metadata.json file +]")

        data = {
            "metadataAttributes": {
                "contentBaseUuid": content_base_uuid,
                "filename": filename,
                "fileUuid": file_uuid
            }
        }

        filename_metadata_json = f"{filename}.metadata.json"

        file_path = f"/tmp/{filename_metadata_json}"

        with open(file_path, "w+b") as file:
            file.write(json.dumps(data).encode('utf-8'))
            file.seek(0)
            self.s3_client.upload_fileobj(file, self.bucket_name, f"{content_base_uuid}/{filename_metadata_json}")

    def add_file(self, file, content_base_uuid: str, file_uuid: str) -> FileResponseDTO:
        try:
            print("[+ BEDROCK: Adding file to bucket +]")

            file_name = self.__create_unique_filename(basename(file.name))
            file_path = f"{content_base_uuid}/{file_name}"

            response = FileResponseDTO(
                status=0,
                file_url=f"https://{self.bucket_name}.s3.{self.region_name}.amazonaws.com/{file_path}",
                file_name=file_name
            )
            self.s3_client.upload_fileobj(file, self.bucket_name, file_path)
            self.add_metadata_json_file(file_name, content_base_uuid, file_uuid)

        except Exception as exception:
            response.status = 1
            response.err = str(exception)

        return response

    def associate_sub_agents(self, supervisor_id: str, agents_list: list[BedrockSubAgent]) -> str:
        sub_agents = []
        for agent in agents_list:
            agent_name = agent.display_name
            # TODO: Change the default instruction
            association_instruction_base = f"This agent should be called whenever the user is talking about {agent_name}"
            agent_association_data = {
                'sub_agent_alias_arn': agent.alias_arn,
                'sub_agent_instruction': association_instruction_base,
                'sub_agent_association_name': slugify(agent_name),
                'relay_conversation_history': 'TO_COLLABORATOR',
            }
            sub_agents.append(agent_association_data)

            response = self.bedrock_agent.associate_agent_collaborator(
                agentId=supervisor_id,
                agentVersion="DRAFT",
                agentDescriptor={"aliasArn": agent_association_data["sub_agent_alias_arn"]},
                collaboratorName=agent_association_data["sub_agent_association_name"],
                collaborationInstruction=agent_association_data["sub_agent_instruction"],
                relayConversationHistory=agent_association_data["relay_conversation_history"],
            )
            self.agent_for_amazon_bedrock.wait_agent_status_update(supervisor_id)
            self.bedrock_agent.prepare_agent(agentId=supervisor_id)
            self.agent_for_amazon_bedrock.wait_agent_status_update(supervisor_id)

        return response["agentCollaborator"]["collaboratorId"]

    def attach_lambda_function(
        self,
        agent_external_id: str,
        action_group_name: str,
        lambda_arn: str,
        agent_version: str,
        function_schema: List[Dict],
        agent: Agent,
    ):
        action_group = self.bedrock_agent.create_agent_action_group(
            actionGroupExecutor={
                'lambda': lambda_arn
            },
            actionGroupName=action_group_name,
            agentId=agent_external_id,
            agentVersion='DRAFT',
            functionSchema={"functions": function_schema}
        )

        data = {
            'actionGroupId': action_group['agentActionGroup']['actionGroupId'],
            'actionGroupName': action_group['agentActionGroup']['actionGroupName'],
            'actionGroupState': action_group['agentActionGroup']['actionGroupState'],
            'agentVersion': action_group['agentActionGroup']['agentVersion'],
            'functionSchema': action_group['agentActionGroup']['functionSchema'],
            'createdAt': action_group['agentActionGroup']['createdAt'].isoformat(),
            'updatedAt': action_group['agentActionGroup']['updatedAt'].isoformat(),
        }

        agent.metadata['action_group'] = data
        agent.save()

    def create_agent(
        self,
        agent_name: str,
        agent_description: str,
        agent_instructions: str,
        model_id: str = None,
        idle_session_tll_in_seconds: int = 1800,
        memory_configuration: Dict = {},
        tags: Dict = {},
        prompt_override_configuration: List[Dict] = [],
    ) -> str:

        _num_tries = 0
        _agent_created = False
        _agent_id = None
        agent_resource_arn = settings.AGENT_RESOURCE_ROLE_ARN

        kwargs = {}

        if prompt_override_configuration:
            kwargs["promptOverrideConfiguration"] = prompt_override_configuration
            print(prompt_override_configuration)

        if memory_configuration:
            kwargs["memoryConfiguration"] = memory_configuration

        if tags:
            kwargs["tags"] = tags

        if not model_id:
            model_id = self.agent_foundation_model[0]

        while not _agent_created and _num_tries <= 2:
            try:
                create_agent_response = self.bedrock_agent.create_agent(
                    agentName=agent_name,
                    agentResourceRoleArn=agent_resource_arn,
                    description=agent_description.replace(
                        "\n", ""
                    ),
                    idleSessionTTLInSeconds=idle_session_tll_in_seconds,
                    foundationModel=model_id,
                    instruction=agent_instructions,
                    agentCollaboration="DISABLED",
                    **kwargs
                )
                _agent_id = create_agent_response["agent"]["agentId"]
                _agent_created = True
                agent_id = _agent_id
                self.wait_agent_status_update(_agent_id)

            except Exception as e:
                print(
                    f"Error creating agent: {e}\n. Retrying in case it was just waiting to be deleted."
                )
                _num_tries += 1

                if _num_tries <= 2:
                    time.sleep(4)
                    pass
                else:
                    print("Giving up on agent creation after 2 tries.")
                    raise e

        return agent_id

    def create_lambda_function(
        self,
        lambda_name: str,
        agent_external_id: str,
        agent_version: str,
        skill_handler: str,
        source_code_file: bytes,
        function_schema: List[Dict],
        agent: Agent,
    ):

        zip_buffer = BytesIO(source_code_file)

        lambda_role = self.agent_for_amazon_bedrock._create_lambda_iam_role(agent_external_id)
        print("LAMBDA ROLE: ", lambda_role)

        print("CREATING LAMBDA FUNCTION")

        lambda_function = self.lambda_client.create_function(
            FunctionName=lambda_name,
            Runtime='python3.12',
            Timeout=180,
            Role=lambda_role,
            Code={'ZipFile': zip_buffer.getvalue()},
            Handler=skill_handler
        )

        lambda_arn = lambda_function.get("FunctionArn")
        action_group_name = f"{lambda_name}_action_group"

        print("ATTACHING LAMBDA FUNCTION TO AGENT")
        self.attach_lambda_function(
            agent_external_id=agent_external_id,
            action_group_name=action_group_name,
            lambda_arn=lambda_arn,
            agent_version=agent_version,
            function_schema=function_schema,
            agent=agent
        )
        self.agent_for_amazon_bedrock._allow_agent_lambda(
            agent_external_id,
            lambda_name
        )
        return lambda_function

    def delete_file_and_metadata(self, content_base_uuid: str, filename: str):
        print("[+ BEDROCK: Deleteing File and its Metadata +]")

        file = f"{content_base_uuid}/{filename}"
        self.s3_client.delete_object(
            Bucket=self.bucket_name,
            Key=file
        )

        file_metadata = f"{content_base_uuid}/{filename}.metadata.json"
        self.s3_client.delete_object(
            Bucket=self.bucket_name,
            Key=file_metadata
        )

    def delete(self, content_base_uuid: str, content_base_file_uuid: str, filename: str):
        self.delete_file_and_metadata(content_base_uuid, filename)

    def disassociate_sub_agent(self, supervisor_id, supervisor_version, sub_agent_id):
        response = self.bedrock_agent.disassociate_agent_collaborator(
            agentId=supervisor_id,
            agentVersion=supervisor_version,
            collaboratorId=sub_agent_id
        )
        return response

    def invoke_supervisor(
        self,
        supervisor_id: str,
        supervisor_alias_id: str,
        session_id: str,
        prompt: str,
        content_base_uuid: str,
    ):
        print("Invoking supervisor")

        single_filter = {
            "equals": {
                "key": "contentBaseUuid",
                "value": content_base_uuid
            }
        }

        retrieval_configuration = {
            "vectorSearchConfiguration": {
                "filter": single_filter
            }
        }

        sessionState = {
            'knowledgeBaseConfigurations': [
                {
                    'knowledgeBaseId': self.knowledge_base_id,
                    'retrievalConfiguration': retrieval_configuration
                }
            ]
        }

        response = self.bedrock_agent_runtime.invoke_agent(
            agentId=supervisor_id,
            agentAliasId=supervisor_alias_id,
            sessionId=session_id,
            inputText=prompt,
            enableTrace=True,
            sessionState=sessionState,
        )

        full_response = ""

        for event in response['completion']:
            if 'trace' in event:
                # TODO: send trace to webhook
                # print("Trace:", event["trace"])
                pass
            elif 'chunk' in event:
                chunk = event['chunk']
                full_response += chunk['bytes'].decode()

        return full_response

    def start_bedrock_ingestion(self) -> str:
        print("[+ Bedrock: Starting ingestion job +]")
        response = self.bedrock_agent.start_ingestion_job(
            dataSourceId=self.data_source_id,
            knowledgeBaseId=self.knowledge_base_id
        )
        ingestion_job_id = response.get("ingestionJob").get("ingestionJobId")
        return ingestion_job_id

    def get_agent(self, agent_id: str):
        return self.bedrock_agent.get_agent(agentId=agent_id)

    def get_agent_action_group(
        self,
        agent_id: str,
        action_group_id: str,
        agent_version: str,
    ):
        return self.bedrock_agent.get_agent_action_group(
            agentId=agent_id,
            agentVersion=agent_version,
            actionGroupId=action_group_id
        )

    def get_agent_version(self, agent_id: str) -> str:
        agent_version_list: dict = self.bedrock_agent.list_agent_versions(agentId=agent_id)
        last_agent_version = agent_version_list.get("agentVersionSummaries")[0].get("agentVersion")
        return last_agent_version

    def create_agent_alias(self, agent_id: str, alias_name: str) -> Tuple[str, str, str]:
        start = pendulum.now()
        agent_alias = self.bedrock_agent.create_agent_alias(
            agentAliasName=alias_name, agentId=agent_id
        )
        # wait aws create version
        time.sleep(5)
        end = pendulum.now()

        agent_alias_id = agent_alias["agentAlias"]["agentAliasId"]
        agent_alias_arn = agent_alias["agentAlias"]["agentAliasArn"]

        response = self.bedrock_agent.list_agent_versions(
            agentId=agent_id,
        )
        # create_agent_alias is not returning agent version
        agent_alias_version = "DRAFT"
        for version in response["agentVersionSummaries"]:
            print("-----------------Agent Version------------------")
            print(version)
            print("------------------------------------------------")
            created_at = pendulum.instance(version["createdAt"])
            if start <= created_at <= end:
                agent_alias_version = version["agentVersion"]

        return agent_alias_id, agent_alias_arn, agent_alias_version

    def create_supervisor(self, supervisor_name, supervisor_description, supervisor_instructions):
        supervisor_id, supervisor_alias, supervisor_arn = self.agent_for_amazon_bedrock.create_agent(
            agent_collaboration='SUPERVISOR_ROUTER',
            agent_name=supervisor_name,
            agent_description=supervisor_description,
            agent_instructions=supervisor_instructions,
            model_ids=self.supervisor_foundation_model,
        )
        return supervisor_id, supervisor_alias

    def get_bedrock_ingestion_status(self, job_id: str):
        response = self.bedrock_agent.get_ingestion_job(
            dataSourceId=self.data_source_id,
            knowledgeBaseId=self.knowledge_base_id,
            ingestionJobId=job_id,
        )
        status_code = response.get("ResponseMetadata").get("HTTPStatusCode")

        if status_code == 200:
            return response.get("ingestionJob").get("status")

        raise Exception(f"get_ingestion_job returned status code {status_code}")

    def wait_agent_status_update(self, external_id: str):
        self.agent_for_amazon_bedrock.wait_agent_status_update(external_id)

    def list_bedrock_ingestion(self, filter_values: List = ['STARTING', 'IN_PROGRESS']):
        response = self.bedrock_agent.list_ingestion_jobs(
            dataSourceId=self.data_source_id,
            knowledgeBaseId=self.knowledge_base_id,
            filters=[
                {
                    'attribute': 'STATUS',
                    'operator': 'EQ',
                    'values': filter_values
                },
            ]
        )
        return response.get("ingestionJobSummaries")

    def prepare_agent(self, agent_id: str):
        self.bedrock_agent.prepare_agent(agentId=agent_id)
        time.sleep(5)
        return

    def search_data(self, content_base_uuid: str, text: str, number_of_results: int = 5) -> Dict[str, Any]:
        retrieval_config = {
            "vectorSearchConfiguration": {
                "filter": {
                    "equals": {
                        "key": "contentBaseUuid",
                        "value": content_base_uuid
                    }
                },
                "numberOfResults": number_of_results
            }
        }

        response = self.bedrock_agent_runtime.retrieve(
            knowledgeBaseId=self.knowledge_base_id,
            retrievalConfiguration=retrieval_config,
            retrievalQuery={
                "text": text
            }
        )
        status: str = response.get("ResponseMetadata").get("HTTPStatusCode")
        chunks = response.get("retrievalResults")

        llm_chunk_list: List[Dict] = self.__format_search_data_response(chunks)

        return {
            "status": status,
            "data": {
                "response": llm_chunk_list
            }
        }

    def create_presigned_url(self, file_name: str, expiration: int = 3600) -> str:
        return self.s3_client.generate_presigned_url('get_object', Params={'Bucket': self.bucket_name, 'Key': file_name}, ExpiresIn=expiration)

    def __format_search_data_response(self, chunks: List[str], ) -> List[Dict]:
        llm_chunk_list = []

        for chunk in chunks:
            llm_chunk_list.append(
                {
                    "full_page": chunk.get("content").get("text"),
                    "filename": chunk.get("metadata").get("filename"),
                    "file_uuid": chunk.get("metadata").get("fileUuid"),
                }
            )

        return llm_chunk_list

    def __create_unique_filename(self, filename: str) -> str:
        name, extension = filename.rsplit(".", 1)
        name = name.replace(".", "_")
        filename = f"{name}-{uuid.uuid4()}.{extension}"
        return filename

    def __get_s3_client(self):
        return boto3.client(
            "s3",
            region_name=self.region_name
        )

    def __get_bedrock_agent(self):
        return boto3.client(
            "bedrock-agent",
            region_name=self.region_name
        )

    def __get_bedrock_agent_runtime(self):
        return boto3.client(
            "bedrock-agent-runtime",
            region_name=self.region_name
        )

    def __get_bedrock_runtime(self):
        return boto3.client(
            "bedrock-runtime",
            region_name=self.region_name
        )

    def __get_lambda_client(self):
        return boto3.client(
            "lambda",
            region_name=self.region_name
        )

    def update_lambda_function(
        self,
        lambda_name: str,
        zip_content: bytes,
    ):
        """
        Updates the code of an existing Lambda function and updates its alias.

        Args:
            lambda_name: The name of the Lambda function to update
            zip_content: The function code to update, packaged as bytes in .zip format
        """
        zip_buffer = BytesIO(zip_content)

        try:
            # Update function code and publish new version
            response = self.lambda_client.update_function_code(
                FunctionName=lambda_name,
                ZipFile=zip_buffer.getvalue(),
                Publish=True  # Create a new version
            )

            # Wait for the function to be updated
            print(" WAITING FOR FUNCTION TO BE UPDATED ...")
            waiter = self.lambda_client.get_waiter('function_updated')
            waiter.wait(
                FunctionName=lambda_name,
                WaiterConfig={
                    'Delay': 5,
                    'MaxAttempts': 60
                }
            )

            # Get the new version number from the response
            new_version = response['Version']

            print(" UPDATING ALIAS TO POINT TO THE NEW VERSION ...")
            print("ALIAS ARGS: ", lambda_name, 'live', new_version)

            try:
                # Try to update the alias
                self.lambda_client.update_alias(
                    FunctionName=lambda_name,
                    Name='live',
                    FunctionVersion=new_version
                )
            except self.lambda_client.exceptions.ResourceNotFoundException:
                # If alias doesn't exist, create it
                print(f"Alias 'live' not found for function {lambda_name}, creating...")
                self.lambda_client.create_alias(
                    FunctionName=lambda_name,
                    Name='live',
                    FunctionVersion=new_version,
                    Description='Production alias for the skill'
                )

            return response

        except Exception as e:
            print(f"Error updating Lambda function {lambda_name}: {str(e)}")
            raise

    def update_agent_action_group(
        self,
        agent_external_id: str,
        action_group_name: str,
        lambda_arn: str,
        agent_version: str,
        action_group_id: str,
        function_schema: List[Dict]
    ):
        """
        Updates an existing action group for an agent.
        """
        print("SCHEMA UPDATE: ", function_schema)
        response = self.bedrock_agent.update_agent_action_group(
            actionGroupExecutor={
                'lambda': lambda_arn
            },
            actionGroupName=action_group_name,
            agentId=agent_external_id,
            actionGroupId=action_group_id,
            agentVersion="DRAFT",
            functionSchema={"functions": function_schema}
        )
        return response
