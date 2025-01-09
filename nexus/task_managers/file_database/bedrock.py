import uuid
import json
import time
from typing import Dict, List, Any, Tuple
from os.path import basename

from io import BytesIO

import boto3
from django.conf import settings

from nexus.task_managers.file_database.file_database import FileDataBase, FileResponseDTO
from nexus.agents.src.utils.bedrock_agent_helper import AgentsForAmazonBedrock

from django.template.defaultfilters import slugify  

from nexus.celery import app as celery_app

from dataclasses import dataclass


@dataclass
class BedrockSubAgent:
    display_name: str
    slug: str
    external_id: str
    alias_arn: str


class BedrockFileDatabase(FileDataBase):
    def __init__(self) -> None:
        self.data_source_id = settings.AWS_BEDROCK_DATASOURCE_ID
        self.knowledge_base_id = settings.AWS_BEDROCK_KNOWLEDGE_BASE_ID
        self.region_name = settings.AWS_BEDROCK_REGION_NAME
        self.bucket_name = settings.AWS_BEDROCK_BUCKET_NAME
        # self.access_key = settings.AWS_BEDROCK_ACCESS_KEY
        # self.secret_key = settings.AWS_BEDROCK_SECRET_KEY
        self.model_id = settings.AWS_BEDROCK_MODEL_ID

        self.s3_client = self.__get_s3_client()
        self.bedrock_agent = self.__get_bedrock_agent()
        self.bedrock_agent_runtime = self.__get_bedrock_agent_runtime()
        self.bedrock_runtime = self.__get_bedrock_runtime()
        self.lambda_client = self.__get_lambda_client()

        self.agent_for_amazon_bedrock = AgentsForAmazonBedrock()

        # TODO: Move this to settings
        self.agent_foundation_model = [
            "amazon.nova-lite-v1:0"
        ]

    def prepare_agent(self, agent_id: str):
        self.bedrock_agent.prepare_agent(agentId=agent_id)
        time.sleep(5)
        return

    def get_agent(self, agent_id: str):
        return self.bedrock_agent.get_agent(agentId=agent_id)

    def get_agent_version(self, agent_id: str):
        agent_version_list: dict = self.bedrock_agent.list_agent_versions(agentId=agent_id)
        last_agent_version = agent_version_list.get("agentVersionSummaries")[0].get("agentVersion")
        return last_agent_version

    def create_supervisor(self, supervisor_name, supervisor_description, supervisor_instructions):
        supervisor_id, supervisor_alias, supervisor_arn = self.agent_for_amazon_bedrock.create_agent(
            agent_collaboration='SUPERVISOR_ROUTER',
            agent_name=supervisor_name,
            agent_description=supervisor_description,
            agent_instructions=supervisor_instructions,
            model_ids=self.agent_foundation_model,
        )
        return supervisor_id

    def create_agent_alias(self, agent_id: str, alias_name: str):
        sub_agent_alias_id, sub_agent_alias_arn = self.agent_for_amazon_bedrock.create_agent_alias(
            agent_id=agent_id, alias_name=alias_name
        )
        return sub_agent_alias_id, sub_agent_alias_arn

    def associate_sub_agents(self, supervisor_id: str, agents_list: list[BedrockSubAgent]) -> Tuple[str, str]:

        sub_agents = []
        for agent in agents_list:
            agent_name = agent.display_name
            association_instruction_base = f"This agent should be called whenever the user is talking about {agent_name}"
            agent_association_data = {
                'sub_agent_alias_arn': agent.alias_arn,
                'sub_agent_instruction': association_instruction_base,
                'sub_agent_association_name': slugify(agent_name),
                'relay_conversation_history': 'TO_COLLABORATOR',
            }
            sub_agents.append(agent_association_data)

        supervisor_agent_alias_id, supervisor_agent_alias_arn = self.agent_for_amazon_bedrock.associate_sub_agents(
            supervisor_agent_id=supervisor_id,
            sub_agents_list=sub_agents,
        )
        return supervisor_agent_alias_id, supervisor_agent_alias_arn

    def create_agent(self, agent_name: str, agent_description: str, agent_instructions: str) -> Tuple[str, str, str]:
        agent_id, agent_alias, agent_arn = self.agent_for_amazon_bedrock.create_agent(
            agent_name=agent_name,
            agent_description=agent_description,
            agent_instructions=agent_instructions,
            model_ids=self.agent_foundation_model,
            agent_collaboration="DISABLED",
            code_interpretation=False
        )
        time.sleep(5)
        return agent_id, agent_alias, agent_arn

    def attach_lambda_function(
        self,
        agent_external_id: str,
        action_group_name: str,
        lambda_arn: str,
    ):
        self.bedrock_agent.create_agent_action_group(
            actionGroupExecutor={
                'lambda': lambda_arn
            },
            actionGroupName=action_group_name,
            agentId=agent_external_id,
            agentVersion='DRAFT',
        )

    def create_lambda_function(
        self,
        lambda_name: str,
        agent_external_id: str,
        agent_version: str,
        source_code_file: bytes,
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
            Handler='lambda_function.lambda_handler'
        )
        print("++++++++++++++++++++++++++++++")
        print("LAMBDA CREATION: ")
        print(lambda_function)
        print("++++++++++++++++++++++++++++++")

        lambda_arn = lambda_function.get("FunctionArn")
        action_group_name = f"{lambda_name}_action_group"

        print("++++++++++++++++++++++++++++++")
        print("ATTACHING LAMBDA FUNCTION TO AGENT")
        self.attach_lambda_function(
            agent_external_id=agent_external_id,
            action_group_name=action_group_name,
            lambda_arn=lambda_arn,
            agent_version=agent_version
        )
        print("++++++++++++++++++++++++++++++")
        return lambda_function

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
            # aws_access_key_id=self.access_key,
            # aws_secret_access_key=self.secret_key,
            region_name=self.region_name
        )

    def __get_bedrock_agent(self):
        return boto3.client(
            "bedrock-agent",
            # aws_access_key_id=self.access_key,
            # aws_secret_access_key=self.secret_key,
            region_name=self.region_name
        )

    def __get_bedrock_agent_runtime(self):
        return boto3.client(
            "bedrock-agent-runtime",
            # aws_access_key_id=self.access_key,
            # aws_secret_access_key=self.secret_key,
            region_name=self.region_name
        )

    def __get_bedrock_runtime(self):
        return boto3.client(
            "bedrock-runtime",
            # aws_access_key_id=self.access_key,
            # aws_secret_access_key=self.secret_key,
            region_name=self.region_name
        )

    def __get_lambda_client(self):
        # try:
        #     assume_role_policy_document = {
        #         "Version": "2012-10-17",
        #         "Statement": [
        #             {
        #                 "Effect": "Allow",
        #                 "Action": "bedrock:InvokeModel",
        #                 "Principal": {
        #                     "Service": "lambda.amazonaws.com"
        #                 },
        #                 "Action": "sts:AssumeRole"
        #             }
        #         ]
        #     }

        #     assume_role_policy_document_json = json.dumps(assume_role_policy_document)

        #     lambda_iam_role = iam_client.create_role(
        #         RoleName=lambda_role_name,
        #         AssumeRolePolicyDocument=assume_role_policy_document_json
        #     )

        #     # Pause to make sure role is created
        #     time.sleep(10)
        #     except:
        #         lambda_iam_role = iam_client.get_role(RoleName=lambda_role_name)

        #     iam_client.attach_role_policy(
        #         RoleName=lambda_role_name,
        #         PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
        # )

        return boto3.client(
            "lambda",
            # aws_access_key_id=self.access_key,
            # aws_secret_access_key=self.secret_key,
            region_name=self.region_name
        )


@celery_app.task
def run_create_lambda_function(
    lambda_name: str,
    agent_external_id: str,
    zip_content: bytes,
    agent_version: str,
    file_database=BedrockFileDatabase
):
    return file_database().create_lambda_function(
        lambda_name=lambda_name,
        agent_external_id=agent_external_id,
        agent_version=agent_version,
        source_code_file=zip_content
    )
