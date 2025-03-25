import uuid
import json
import time
from typing import TYPE_CHECKING
from datetime import datetime

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

from nexus.agents.models import Agent, Credential
from nexus.agents.components import get_all_formats

if TYPE_CHECKING:
    from router.entities import Message
    from nexus.intelligences.models import ContentBase


@dataclass
class BedrockSubAgent:
    display_name: str
    slug: str
    external_id: str
    agent_instructions: str
    description: str
    foundation_model: str = None


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

        self.account_id = self.__get_sts_client().get_caller_identity()["Account"]
        self.iam_client = self.__get_iam_client()
        self.bedrock_agent = self.__get_bedrock_agent()
        self.bedrock_agent_runtime = self.__get_bedrock_agent_runtime()
        self.bedrock_runtime = self.__get_bedrock_runtime()
        self.lambda_client = self.__get_lambda_client()
        self.s3_client = self.__get_s3_client()

        self._suffix = f"{self.region_name}-{self.account_id}"
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

    def add_metadata_json_file(self, filename: str, content_base_uuid: str, file_uuid: str):
        import os
        import tempfile
        from io import BytesIO
        print("[+ BEDROCK: Adding metadata.json file +]")

        data = {
            "metadataAttributes": {
                "contentBaseUuid": content_base_uuid,
                "filename": filename,
                "fileUuid": file_uuid
            }
        }

        filename_metadata_json = f"{filename}.metadata.json"
        key = f"{content_base_uuid}/{filename_metadata_json}"
        print("\n\n\n\n\n")
        print(filename_metadata_json)
        print(key)
        print("\n\n\n\n\n")
        bytes_stream = BytesIO(json.dumps(data).encode('utf-8'))
        self.s3_client.upload_fileobj(bytes_stream, self.bucket_name, key)

    def multipart_upload(self, file, content_base_uuid: str, file_uuid: str, part_size: int = 5 * 1024 * 1024):
        from io import BytesIO
        s3_client = self.s3_client
        bucket_name = self.bucket_name
        file_name = self.__create_unique_filename(basename(file.name))
        key = f"{content_base_uuid}/{file_name}"

        response = s3_client.create_multipart_upload(Bucket=bucket_name, Key=key)
        upload_id = response['UploadId']

        parts = []
        try:
            part_number = 1
            while True:
                data = file.read(part_size)
                if not data:
                    break

                response = s3_client.upload_part(
                    Bucket=bucket_name,
                    Key=key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=data
                )
                part_info = {'PartNumber': part_number, 'ETag': response['ETag']}
                parts.append(part_info)
                part_number += 1
            
            response = s3_client.complete_multipart_upload(
                Bucket=bucket_name,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )

            print(f"Upload finalizado: {response['Location']}")
            return file_name, response['Location']

        except Exception as e:
            print(f"Erro no upload: {e}")
            s3_client.abort_multipart_upload(Bucket=bucket_name, Key=key, UploadId=upload_id)

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
        lambda_role = settings.AGENT_RESOURCE_ROLE_ARN
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
        return lambda_function

    def invoke_inline_agent(
        self,
        session_id: str,
        input_text: str,
        instruction: str,
        foundation_model: str = None,
        action_groups: List[Dict] = None,
        knowledge_bases: List[Dict] = None,
        collaborator_configurations: Dict = None,
        collaborators: List[Dict] = None,
        prompt_override_configuration: Dict = None,
        guardrail_configuration: Dict = None,
        enable_trace: bool = True,
        idle_session_ttl_in_seconds: int = 1800,
        end_session: bool = False,
        inline_session_state: Dict = None,
        customer_encryption_key_arn: str = None,
    ):
        """
        Invoke an inline agent with the specified configuration.
        
        Args:
            session_id: Unique identifier for the conversation session
            input_text: User input text to send to the agent
            instruction: Instructions for the agent
            foundation_model: Model ID to use for the agent
            action_groups: List of action groups the agent can use
            knowledge_bases: List of knowledge bases the agent can use
            collaborator_configurations: Configuration for collaborator agents
            collaborators: List of collaborator agents
            prompt_override_configuration: Configuration to override the default prompts
            guardrail_configuration: Configuration for guardrails
            enable_trace: Whether to enable tracing
            idle_session_ttl_in_seconds: Time after which the session expires
            end_session: Whether to end the session
            inline_session_state: State to persist through the session
            customer_encryption_key_arn: ARN of KMS key to encrypt agent resources
            
        Returns:
            Response from the inline agent
        """
        if not foundation_model:
            foundation_model = self.agent_foundation_model[0]
            
        params = {
            "sessionId": session_id,
            "inputText": input_text,
            "instruction": instruction,
            "foundationModel": foundation_model,
            "enableTrace": enable_trace,
            "endSession": end_session,
            "idleSessionTTLInSeconds": idle_session_ttl_in_seconds,
        }
        
        if action_groups:
            params["actionGroups"] = action_groups
            
        if knowledge_bases:
            params["knowledgeBases"] = knowledge_bases
            
        if collaborator_configurations:
            params["collaboratorConfigurations"] = collaborator_configurations
            
        if collaborators:
            params["collaborators"] = collaborators
            
        if prompt_override_configuration:
            params["promptOverrideConfiguration"] = prompt_override_configuration
            
        if guardrail_configuration:
            params["guardrailConfiguration"] = guardrail_configuration
            
        if inline_session_state:
            params["inlineSessionState"] = inline_session_state
            
        if customer_encryption_key_arn:
            params["customerEncryptionKeyArn"] = customer_encryption_key_arn
            
        return self.bedrock_agent_runtime.invoke_inline_agent(**params)

    def invoke_inline_agent_stream(
        self,
        session_id: str,
        input_text: str,
        instruction: str,
        content_base: "ContentBase",
        message: "Message",
        foundation_model: str = None,
        action_groups: List[Dict] = None,
        enable_trace: bool = True,
    ):
        """
        Invoke an inline agent with streaming response.
        
        Args:
            session_id: Unique identifier for the conversation session
            input_text: User input text to send to the agent
            instruction: Instructions for the agent
            content_base: Content base to use for the agent
            message: Message object with user input
            foundation_model: Model ID to use for the agent
            action_groups: List of action groups the agent can use
            enable_trace: Whether to enable tracing
            
        Yields:
            Streaming response chunks from the inline agent
        """
        print("Invoking inline agent with streaming")

        content_base_uuid = str(content_base.uuid)
        agent = content_base.agent
        instructions = content_base.instructions.all()

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

        knowledge_bases = [{
            "knowledgeBaseId": self.knowledge_base_id,
            "description": "Use this KB to get all the info needed to answer questions",
            "retrievalConfiguration": retrieval_configuration
        }]

        # Prepare session state with credentials
        credentials = {}
        try:
            agent_credentials = Credential.objects.filter(project_id=message.project_uuid)
            for credential in agent_credentials:
                credentials[credential.key] = credential.decrypted_value
        except Exception as e:
            print(f"Error fetching credentials: {str(e)}")

        # Set up session attributes
        session_attributes = {
            "credentials": json.dumps(credentials, default=str)
        }

        # Set up prompt session attributes
        prompt_session_attributes = {
            "contact_urn": message.contact_urn,
            "contact_fields": message.contact_fields_as_json,
            "date_time_now": pendulum.now("America/Sao_Paulo").isoformat(),
            "project_id": message.project_uuid,
            "specific_personality": json.dumps({
                "occupation": agent.role,
                "name": agent.name,
                "goal": agent.goal,
                "adjective": agent.personality,
                "instructions": list(instructions.values_list("instruction", flat=True))
            })
        }

        # Configure inline session state
        inline_session_state = {
            "sessionAttributes": session_attributes,
            "promptSessionAttributes": prompt_session_attributes
        }

        # Set up guardrail if configured
        guardrail_configuration = None
        if hasattr(settings, "AWS_BEDROCK_GUARDRAIL_IDENTIFIER") and settings.AWS_BEDROCK_GUARDRAIL_IDENTIFIER:
            guardrail_configuration = {
                "guardrailIdentifier": settings.AWS_BEDROCK_GUARDRAIL_IDENTIFIER,
                "guardrailVersion": settings.AWS_BEDROCK_GUARDRAIL_VERSION
            }

        # Default action groups, including UserInput
        if not action_groups:
            action_groups = [
                {
                    "name": "UserInputAction",
                    "parentActionGroupSignature": "AMAZON.UserInput"
                }
            ]

        # Add Code Interpreter if needed
        if getattr(settings, "ENABLE_CODE_INTERPRETER", False):
            action_groups.append({
                "name": "CodeInterpreterAction",
                "parentActionGroupSignature": "AMAZON.CodeInterpreter"
            })

        if not foundation_model:
            foundation_model = self.agent_foundation_model[0]

        # Call the inline agent with streaming
        response = self.bedrock_agent_runtime.invoke_inline_agent(
            sessionId=session_id,
            foundationModel=foundation_model,
            instruction=instruction,
            inputText=input_text,
            enableTrace=enable_trace,
            actionGroups=action_groups,
            knowledgeBases=knowledge_bases,
            inlineSessionState=inline_session_state,
            guardrailConfiguration=guardrail_configuration
        )

        # Process and yield streaming response
        for event in response.get('completion', []):
            if 'chunk' in event:
                chunk = event['chunk']
                yield {
                    'type': 'chunk',
                    'content': chunk['bytes'].decode()
                }
            elif 'trace' in event:
                trace_data = event['trace']
                print("Trace:", trace_data)
                yield {
                    'type': 'trace',
                    'content': {
                        'sessionId': session_id,
                        'trace': trace_data
                    }
                }

    def start_bedrock_ingestion(self) -> str:
        print("[+ Bedrock: Starting ingestion job +]")
        response = self.bedrock_agent.start_ingestion_job(
            dataSourceId=self.data_source_id,
            knowledgeBaseId=self.knowledge_base_id
        )
        ingestion_job_id = response.get("ingestionJob").get("ingestionJobId")
        return ingestion_job_id

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

    def __get_iam_client(self):
        return boto3.client(
            "iam",
            region_name=self.region_name
        )

    def __get_sts_client(self):
        return boto3.client(
            "sts",
            region_name=self.region_name
        )

    def _allow_agent_lambda(self, lambda_function_name: str) -> None:
        """
        Grant Lambda invocation permissions to the inline agent.
        """
        self.lambda_client.add_permission(
            FunctionName=lambda_function_name,
            StatementId=f"allow_bedrock_inline_{uuid.uuid4()}",
            Action="lambda:InvokeFunction",
            Principal="bedrock.amazonaws.com",
            SourceArn=f"arn:aws:bedrock:{self.region_name}:{self.account_id}:*",
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

    def upload_traces(self, data, key):
        bytes_stream = BytesIO(data.encode('utf-8'))
        self.s3_client.upload_fileobj(bytes_stream, self.bucket_name, key)

    def get_trace_file(self, key):
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            return response['Body'].read().decode('utf-8')
        except self.s3_client.exceptions.NoSuchKey:
            return []
