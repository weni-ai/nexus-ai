import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from io import BytesIO
from os.path import basename
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Tuple,
)

import boto3
import pendulum
from django.conf import settings
from django.template.defaultfilters import slugify

from nexus.agents.components import get_all_formats_list
from nexus.agents.models import Agent, Credential, Team
from nexus.task_managers.file_database.file_database import FileDataBase, FileResponseDTO
from nexus.utils import get_datasource_id

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from nexus.intelligences.models import ContentBase
    from router.entities import Message


@dataclass
class BedrockSubAgent:
    display_name: str
    slug: str
    external_id: str
    alias_arn: str
    description: str


class BedrockFileDatabase(FileDataBase):
    def __init__(
        self,
        agent_foundation_model: List = settings.AWS_BEDROCK_AGENTS_MODEL_ID,
        supervisor_foundation_model: List = settings.AWS_BEDROCK_SUPERVISOR_MODEL_ID,
        project_uuid: str | None = None,
    ) -> None:
        self.data_source_id = get_datasource_id(project_uuid)
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
            "prompt": prompt,
        }

        payload = json.dumps(data)
        response = self.bedrock_runtime.invoke_model(
            body=payload,
            contentType="application/json",
            accept="application/json",
            modelId=self.model_id,
            trace="ENABLED",
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
        required_fields = ["agentId", "agentName", "agentResourceRoleArn", "foundationModel", "agentCollaboration"]

        # Preserve existing agent collaboration
        _agent_details["agentCollaboration"] = _agent_details.get("agentCollaboration", "DISABLED")

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
            key for key in _agent_details.keys() if key not in updated_fields and key not in required_fields
        ]

        for key in keys_to_remove:
            del _agent_details[key]

        _update_agent_response = self.bedrock_agent.update_agent(**_agent_details)

        time.sleep(3)

        return _update_agent_response

    def add_metadata_json_file(self, filename: str, content_base_uuid: str, file_uuid: str):
        from io import BytesIO

        logger.info("[Bedrock] Adding metadata.json file")

        data = {
            "metadataAttributes": {"contentBaseUuid": content_base_uuid, "filename": filename, "fileUuid": file_uuid}
        }

        filename_metadata_json = f"{filename}.metadata.json"
        key = f"{content_base_uuid}/{filename_metadata_json}"
        logger.debug("Bedrock metadata file", extra={"filename": filename_metadata_json, "key": key})
        bytes_stream = BytesIO(json.dumps(data).encode("utf-8"))
        self.s3_client.upload_fileobj(bytes_stream, self.bucket_name, key)

    def multipart_upload(self, file, content_base_uuid: str, file_uuid: str, part_size: int = 5 * 1024 * 1024):
        s3_client = self.s3_client
        bucket_name = self.bucket_name
        file_name = self.__create_unique_filename(basename(file.name))
        key = f"{content_base_uuid}/{file_name}"

        response = s3_client.create_multipart_upload(Bucket=bucket_name, Key=key)
        upload_id = response["UploadId"]

        parts = []
        try:
            part_number = 1
            while True:
                data = file.read(part_size)
                if not data:
                    break

                response = s3_client.upload_part(
                    Bucket=bucket_name, Key=key, PartNumber=part_number, UploadId=upload_id, Body=data
                )
                part_info = {"PartNumber": part_number, "ETag": response["ETag"]}
                parts.append(part_info)
                part_number += 1

            response = s3_client.complete_multipart_upload(
                Bucket=bucket_name, Key=key, UploadId=upload_id, MultipartUpload={"Parts": parts}
            )

            logger.info("Upload finished", extra={"location": response["Location"]})
            return file_name, response["Location"]

        except Exception as e:
            logger.error("Error on upload: %s", e, exc_info=True)
            s3_client.abort_multipart_upload(Bucket=bucket_name, Key=key, UploadId=upload_id)

    def add_file(self, file, content_base_uuid: str, file_uuid: str) -> FileResponseDTO:
        try:
            logger.info("[Bedrock] Adding file to bucket")

            file_name = self.__create_unique_filename(basename(file.name))
            file_path = f"{content_base_uuid}/{file_name}"

            response = FileResponseDTO(
                status=0,
                file_url=f"https://{self.bucket_name}.s3.{self.region_name}.amazonaws.com/{file_path}",
                file_name=file_name,
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
            association_instruction_base = agent.description
            agent_association_data = {
                "sub_agent_alias_arn": agent.alias_arn,
                "sub_agent_instruction": association_instruction_base,
                "sub_agent_association_name": slugify(agent_name),
                "relay_conversation_history": "TO_COLLABORATOR",
            }
            sub_agents.append(agent_association_data)

            logger.debug(
                "Agent association data",
                extra={
                    "supervisor_id": supervisor_id,
                    "alias_arn_suffix": agent_association_data["sub_agent_alias_arn"][-10:],
                    "association_name": agent_association_data["sub_agent_association_name"],
                    "relay_history": agent_association_data["relay_conversation_history"],
                },
            )

            response = self.bedrock_agent.associate_agent_collaborator(
                agentId=supervisor_id,
                agentVersion="DRAFT",
                agentDescriptor={"aliasArn": agent_association_data["sub_agent_alias_arn"]},
                collaboratorName=agent_association_data["sub_agent_association_name"],
                collaborationInstruction=agent_association_data["sub_agent_instruction"],
                relayConversationHistory=agent_association_data["relay_conversation_history"],
            )

            self.wait_agent_status_update(supervisor_id)
            self.bedrock_agent.prepare_agent(agentId=supervisor_id)
            self.wait_agent_status_update(supervisor_id)

        return response["agentCollaborator"]["collaboratorId"]

    def attach_lambda_function(
        self,
        agent_external_id: str,
        action_group_name: str,
        lambda_arn: str,
        agent_version: str,
        function_schema: List[Dict],
        agent: Agent,
    ) -> Dict:
        """Attaches a lambda function to an agent and returns the response"""
        action_group = self.bedrock_agent.create_agent_action_group(
            actionGroupExecutor={"lambda": lambda_arn},
            actionGroupName=action_group_name,
            agentId=agent_external_id,
            agentVersion="DRAFT",
            functionSchema={"functions": function_schema},
        )

        data = {
            "actionGroupId": action_group["agentActionGroup"]["actionGroupId"],
            "actionGroupName": action_group["agentActionGroup"]["actionGroupName"],
            "actionGroupState": action_group["agentActionGroup"]["actionGroupState"],
            "agentVersion": action_group["agentActionGroup"]["agentVersion"],
            "functionSchema": action_group["agentActionGroup"]["functionSchema"],
            "createdAt": action_group["agentActionGroup"]["createdAt"].isoformat(),
            "updatedAt": action_group["agentActionGroup"]["updatedAt"].isoformat(),
        }

        agent.metadata["action_group"] = data
        agent.save()

        return action_group

    def attach_supervisor_lambda_function(
        self,
        agent_external_id: str,
        action_group_name: str,
        lambda_arn: str,
        function_schema: List[Dict],
        team: Team,
    ) -> Dict:
        """Attaches a lambda function to supervisor team and returns the response"""
        action_group = self.bedrock_agent.create_agent_action_group(
            actionGroupExecutor={"lambda": lambda_arn},
            actionGroupName=action_group_name,
            agentId=agent_external_id,
            agentVersion="DRAFT",
            functionSchema={"functions": function_schema},
        )

        data = {
            "actionGroupId": action_group["agentActionGroup"]["actionGroupId"],
            "actionGroupName": action_group["agentActionGroup"]["actionGroupName"],
            "actionGroupState": action_group["agentActionGroup"]["actionGroupState"],
            "agentVersion": action_group["agentActionGroup"]["agentVersion"],
            "functionSchema": action_group["agentActionGroup"]["functionSchema"],
            "createdAt": action_group["agentActionGroup"]["createdAt"].isoformat(),
            "updatedAt": action_group["agentActionGroup"]["updatedAt"].isoformat(),
        }

        team.metadata["action_group"] = data
        team.save()

        return action_group

    def attach_agent_knowledge_base(
        self,
        agent_id: str,
        agent_version: str,
        knowledge_base_instruction: str,
        knowledge_base_id: str,
    ):
        self.bedrock_agent.associate_agent_knowledge_base(
            agentId=agent_id,
            agentVersion=agent_version,
            description=knowledge_base_instruction,
            knowledgeBaseId=knowledge_base_id,
        )

    def create_agent(
        self,
        agent_name: str,
        agent_description: str,
        agent_instructions: str,
        model_id: Optional[str] = None,
        idle_session_tll_in_seconds: int = 1800,
        memory_configuration: Optional[Dict] = None,
        tags: Optional[Dict] = None,
        prompt_override_configuration: Optional[List[Dict]] = None,
    ) -> str:
        if memory_configuration is None:
            memory_configuration = {}
        if tags is None:
            tags = {}
        if prompt_override_configuration is None:
            prompt_override_configuration = []
        _num_tries = 0
        _agent_created = False
        _agent_id = None
        agent_resource_arn = settings.AGENT_RESOURCE_ROLE_ARN

        kwargs = {}

        if prompt_override_configuration:
            kwargs["promptOverrideConfiguration"] = prompt_override_configuration
            logger.debug("promptOverrideConfiguration present", extra={"has": True})

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
                    description=agent_description.replace("\n", ""),
                    idleSessionTTLInSeconds=idle_session_tll_in_seconds,
                    foundationModel=model_id,
                    instruction=agent_instructions,
                    agentCollaboration="DISABLED",
                    **kwargs,
                )
                _agent_id = create_agent_response["agent"]["agentId"]
                _agent_created = True
                agent_id = _agent_id
                self.wait_agent_status_update(_agent_id)

            except Exception as e:
                logger.error("Error creating agent: %s. Retrying if pending deletion.", e)
                _num_tries += 1

                if _num_tries <= 2:
                    time.sleep(4)
                    pass
                else:
                    logger.error("Giving up on agent creation after 2 tries.")
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

        # lambda_role = self._create_lambda_iam_role(agent_external_id)
        lambda_role = settings.AGENT_RESOURCE_ROLE_ARN
        logger.info("Lambda role configured", extra={"role_suffix": str(lambda_role)[-8:]})

        logger.info("Creating Lambda function")

        lambda_function = self.lambda_client.create_function(
            FunctionName=lambda_name,
            Runtime="python3.12",
            Timeout=180,
            Role=lambda_role,
            Code={"ZipFile": zip_buffer.getvalue()},
            Handler=skill_handler,
        )

        lambda_arn = lambda_function.get("FunctionArn")
        action_group_name = f"{lambda_name}_action_group"

        logger.info("Attaching Lambda function to agent")
        self.attach_lambda_function(
            agent_external_id=agent_external_id,
            action_group_name=action_group_name,
            lambda_arn=lambda_arn,
            agent_version=agent_version,
            function_schema=function_schema,
            agent=agent,
        )
        self.allow_agent_lambda(agent_external_id, lambda_name)
        return lambda_function

    def delete_file_and_metadata(self, content_base_uuid: str, filename: str):
        logger.info("[Bedrock] Deleting file and metadata")

        file = f"{content_base_uuid}/{filename}"
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=file)

        file_metadata = f"{content_base_uuid}/{filename}.metadata.json"
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_metadata)

    def delete(self, content_base_uuid: str, content_base_file_uuid: str, filename: str):
        self.delete_file_and_metadata(content_base_uuid, filename)

    def disassociate_sub_agent(self, supervisor_id, supervisor_version, sub_agent_id):
        response = self.bedrock_agent.disassociate_agent_collaborator(
            agentId=supervisor_id, agentVersion=supervisor_version, collaboratorId=sub_agent_id
        )
        return response

    def bedrock_agent_to_supervisor(self, agent_id: str, to_supervisor: bool = True):
        agent_to_update = self.bedrock_agent.get_agent(agentId=agent_id)
        agent_to_update = agent_to_update["agent"]

        try:
            memory_configuration = agent_to_update["memoryConfiguration"]
        except KeyError:
            memory_configuration = {
                "enabledMemoryTypes": ["SESSION_SUMMARY"],
                "sessionSummaryConfiguration": {"maxRecentSessions": 5},
                "storageDays": 30,
            }

        agent_collaboration = {True: "SUPERVISOR", False: "DISABLED"}

        self.wait_agent_status_update(agent_id)

        guardrail_configuration = agent_to_update.get("guardrailConfiguration")

        if not guardrail_configuration:
            guardrail_configuration = {
                "guardrailIdentifier": settings.AWS_BEDROCK_GUARDRAIL_IDENTIFIER,
                "guardrailVersion": settings.AWS_BEDROCK_GUARDRAIL_VERSION,
            }

        self.bedrock_agent.update_agent(
            agentId=agent_to_update["agentId"],
            agentName=agent_to_update["agentName"],
            agentResourceRoleArn=agent_to_update["agentResourceRoleArn"],
            agentCollaboration=agent_collaboration.get(to_supervisor),
            instruction=agent_to_update["instruction"],
            foundationModel=agent_to_update["foundationModel"],
            memoryConfiguration=memory_configuration,
            guardrailConfiguration=guardrail_configuration,
        )

    def delete_agent(self, agent_id: str):
        self.bedrock_agent.delete_agent(agentId=agent_id)

    def invoke_supervisor_stream(
        self,
        supervisor_id: str,
        supervisor_alias_id: str,
        session_id: str,
        content_base: "ContentBase",
        message: "Message",
    ):
        logger.info("Invoking supervisor with streaming")

        content_base_uuid = str(content_base.uuid)
        agent = content_base.agent
        instructions = content_base.instructions.all()
        team = Team.objects.get(project__uuid=message.project_uuid)

        single_filter = {"equals": {"key": "contentBaseUuid", "value": content_base_uuid}}

        retrieval_configuration = {"vectorSearchConfiguration": {"filter": single_filter}}

        sessionState = {
            "knowledgeBaseConfigurations": [
                {"knowledgeBaseId": self.knowledge_base_id, "retrievalConfiguration": retrieval_configuration}
            ]
        }

        credentials = {}
        try:
            agent_credentials = Credential.objects.filter(project_id=message.project_uuid)
            for credential in agent_credentials:
                credentials[credential.key] = credential.decrypted_value
        except Exception as e:
            logger.error("Error fetching credentials: %s", str(e))

        sessionState["sessionAttributes"] = {"credentials": json.dumps(credentials, default=str)}

        time_now = pendulum.now("America/Sao_Paulo")
        llm_formatted_time = f"Today is {time_now.format('dddd, MMMM D, YYYY [at] HH:mm:ss z')}"

        sessionState["promptSessionAttributes"] = {
            # "format_components": get_all_formats(),
            "contact_urn": message.contact_urn,
            "contact_fields": message.contact_fields_as_json,
            "date_time_now": llm_formatted_time,
            "project_id": message.project_uuid,
            "specific_personality": json.dumps(
                {
                    "occupation": agent.role,
                    "name": agent.name,
                    "goal": agent.goal,
                    "adjective": agent.personality,
                    "instructions": list(instructions.values_list("instruction", flat=True)),
                }
            ),
        }

        if message.project_uuid in settings.PROJECT_COMPONENTS:
            sessionState["promptSessionAttributes"].update(
                {
                    "format_components": get_all_formats_list(),
                }
            )

        if team.human_support:
            sessionState["promptSessionAttributes"].update(
                {
                    "human_support": json.dumps(
                        {
                            "project_id": message.project_uuid,
                            "contact_id": message.contact_urn,
                            "business_rules": team.human_support_prompt,
                        }
                    )
                }
            )

        try:
            response = self.bedrock_agent_runtime.invoke_agent(
                agentId=supervisor_id,
                agentAliasId=supervisor_alias_id,
                sessionId=session_id,
                inputText=message.text,
                enableTrace=True,
                sessionState=sessionState,
            )

            for event in response["completion"]:
                if isinstance(event, dict):
                    if "chunk" in event:
                        chunk = event["chunk"]
                        yield {"type": "chunk", "content": chunk["bytes"].decode()}
                    elif "trace" in event:
                        trace_data = event["trace"]
                        yield {"type": "trace", "content": trace_data}
                    else:
                        logger.debug("Unknown event structure", extra={"event_keys": list(event.keys())})

        except Exception as e:
            logger.error("Error invoking supervisor stream: %s", str(e), exc_info=True)
            raise

    def start_bedrock_ingestion(self) -> str:
        logger.info("[Bedrock] Starting ingestion job")
        response = self.bedrock_agent.start_ingestion_job(
            dataSourceId=self.data_source_id, knowledgeBaseId=self.knowledge_base_id
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
            agentId=agent_id, agentVersion=agent_version, actionGroupId=action_group_id
        )

    def get_agent_version(self, agent_id: str) -> str:
        agent_version_list: dict = self.bedrock_agent.list_agent_versions(agentId=agent_id)
        last_agent_version = agent_version_list.get("agentVersionSummaries")[0].get("agentVersion")
        return last_agent_version

    def create_agent_alias(self, agent_id: str, alias_name: str) -> Tuple[str, str, str]:
        start = pendulum.now()
        agent_alias = self.bedrock_agent.create_agent_alias(agentAliasName=alias_name, agentId=agent_id)
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
            logger.debug("Agent version", extra={"version": version})
            created_at = pendulum.instance(version["createdAt"])
            if start <= created_at <= end:
                agent_alias_version = version["agentVersion"]

        return agent_alias_id, agent_alias_arn, agent_alias_version

    def create_supervisor(
        self,
        supervisor_name: str,
        supervisor_description: str,
        supervisor_instructions: str,
        is_single_agent: bool = False,
    ) -> Tuple[str, str]:
        """
        Creates a new supervisor agent using an existing agent as base.
        Returns tuple of (supervisor_id, supervisor_alias_name)
        """

        agent_collaboration = {True: "DISABLED", False: "SUPERVISOR"}

        # Get existing agent to use as base
        base_agent_response = self.bedrock_agent.get_agent(agentId=settings.AWS_BEDROCK_SUPERVISOR_EXTERNAL_ID)
        base_agent = base_agent_response["agent"]
        memory_configuration = base_agent["memoryConfiguration"]

        # Create new supervisor using base agent's configuration
        response_create_supervisor = self.bedrock_agent.create_agent(
            agentName=supervisor_name,
            description=supervisor_description,
            instruction=base_agent["instruction"],
            agentResourceRoleArn=settings.AGENT_RESOURCE_ROLE_ARN,
            foundationModel=base_agent["foundationModel"],
            idleSessionTTLInSeconds=base_agent["idleSessionTTLInSeconds"],
            agentCollaboration=agent_collaboration.get(is_single_agent),
            guardrailConfiguration={
                "guardrailIdentifier": settings.AWS_BEDROCK_GUARDRAIL_IDENTIFIER,
                "guardrailVersion": str(settings.AWS_BEDROCK_GUARDRAIL_VERSION),
            },
            memoryConfiguration=memory_configuration,
        )

        self.wait_agent_status_update(response_create_supervisor["agent"]["agentId"])
        supervisor_id = response_create_supervisor["agent"]["agentId"]

        lambda_arn = f"{settings.AWS_BEDROCK_LAMBDA_ARN}"

        base_action_group_response = self.get_agent_action_group(
            agent_id=settings.AWS_BEDROCK_SUPERVISOR_EXTERNAL_ID,
            action_group_id=settings.AWS_BEDROCK_SUPERVISOR_ACTION_GROUP_ID,
            agent_version="DRAFT",
        )

        function_schema = base_action_group_response["agentActionGroup"]["functionSchema"]["functions"]
        logger.debug(
            "Function schema fetched", extra={"function_count": len(function_schema) if function_schema else 0}
        )
        for function in function_schema:
            function["name"] = "".join(c for c in function["name"] if c.isalnum() or c in "_-")

        logger.debug(
            "Function schema sanitized", extra={"function_count": len(function_schema) if function_schema else 0}
        )

        self.bedrock_agent.create_agent_action_group(
            actionGroupExecutor={"lambda": lambda_arn},
            actionGroupName=base_action_group_response["agentActionGroup"]["actionGroupName"],
            actionGroupState="ENABLED",
            agentId=supervisor_id,
            agentVersion="DRAFT",
            functionSchema={"functions": function_schema},
        )

        parent_signature = "AMAZON.UserInput"

        self.bedrock_agent.create_agent_action_group(
            actionGroupName="UserInputAction",
            actionGroupState="ENABLED",
            agentId=supervisor_id,
            agentVersion="DRAFT",
            parentActionGroupSignature=parent_signature,
        )

        self.attach_agent_knowledge_base(
            agent_id=supervisor_id,
            agent_version="DRAFT",
            knowledge_base_instruction=settings.AWS_BEDROCK_SUPERVISOR_KNOWLEDGE_BASE_INSTRUCTIONS,
            knowledge_base_id=self.knowledge_base_id,
        )

        # self.prepare_agent(agent_id=supervisor_id)

        return supervisor_id, supervisor_name

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

    def list_bedrock_ingestion(self, filter_values: Optional[List] = None):
        if filter_values is None:
            filter_values = ["STARTING", "IN_PROGRESS"]
        response = self.bedrock_agent.list_ingestion_jobs(
            dataSourceId=self.data_source_id,
            knowledgeBaseId=self.knowledge_base_id,
            filters=[
                {"attribute": "STATUS", "operator": "EQ", "values": filter_values},
            ],
        )
        return response.get("ingestionJobSummaries")

    def prepare_agent(self, agent_id: str):
        self.bedrock_agent.prepare_agent(agentId=agent_id)
        time.sleep(5)
        return

    def search_data(self, content_base_uuid: str, text: str, number_of_results: int = 5) -> Dict[str, Any]:
        combined_filter = {
            "andAll": [
                {"equals": {"key": "contentBaseUuid", "value": content_base_uuid}},
                {"equals": {"key": "x-amz-bedrock-kb-data-source-id", "value": self.data_source_id}},
            ]
        }

        retrieval_config = {
            "vectorSearchConfiguration": {"filter": combined_filter, "numberOfResults": number_of_results}
        }

        response = self.bedrock_agent_runtime.retrieve(
            knowledgeBaseId=self.knowledge_base_id,
            retrievalConfiguration=retrieval_config,
            retrievalQuery={"text": text},
        )
        status: str = response.get("ResponseMetadata").get("HTTPStatusCode")
        chunks = response.get("retrievalResults")

        llm_chunk_list: List[Dict] = self.__format_search_data_response(chunks)

        return {"status": status, "data": {"response": llm_chunk_list}}

    def create_presigned_url(self, file_name: str, expiration: int = 3600) -> str:
        return self.s3_client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket_name, "Key": file_name}, ExpiresIn=expiration
        )

    def __format_search_data_response(
        self,
        chunks: List[str],
    ) -> List[Dict]:
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
        return boto3.client("s3", region_name=self.region_name)

    def __get_bedrock_agent(self):
        return boto3.client("bedrock-agent", region_name=self.region_name)

    def __get_bedrock_agent_runtime(self):
        return boto3.client("bedrock-agent-runtime", region_name=self.region_name)

    def __get_bedrock_runtime(self):
        return boto3.client("bedrock-runtime", region_name=self.region_name)

    def __get_lambda_client(self):
        return boto3.client("lambda", region_name=self.region_name)

    def __get_iam_client(self):
        return boto3.client("iam", region_name=self.region_name)

    def __get_sts_client(self):
        return boto3.client("sts", region_name=self.region_name)

    def allow_agent_lambda(self, agent_id: str, lambda_function_name: str) -> None:
        self.lambda_client.add_permission(
            FunctionName=lambda_function_name,
            StatementId=f"allow_bedrock_{agent_id}",
            Action="lambda:InvokeFunction",
            Principal="bedrock.amazonaws.com",
            SourceArn=f"arn:aws:bedrock:{self.region_name}:{self.account_id}:agent/{agent_id}",
        )

    def remove_agent_lambda(self, agent_id: str, lambda_function_name: str) -> None:
        self.lambda_client.remove_permission(
            FunctionName=lambda_function_name,
            StatementId=f"allow_bedrock_{agent_id}",
        )

    def wait_agent_status_update(self, agent_id):
        response = self.bedrock_agent.get_agent(agentId=agent_id)
        agent_status = response["agent"]["agentStatus"]
        _waited_at_least_once = False
        while agent_status.endswith("ING"):
            logger.info("Waiting for agent status to change", extra={"status": agent_status})
            time.sleep(5)
            _waited_at_least_once = True
            try:
                response = self.bedrock_agent.get_agent(agentId=agent_id)
                agent_status = response["agent"]["agentStatus"]
            except self.bedrock_agent.exceptions.ResourceNotFoundException:
                agent_status = "DELETED"
        if _waited_at_least_once:
            logger.info("Agent current status", extra={"agent_id": agent_id, "status": agent_status})

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
                Publish=True,  # Create a new version
            )

            # Wait for the function to be updated
            logger.info("Waiting for function to be updated")
            waiter = self.lambda_client.get_waiter("function_updated")
            waiter.wait(FunctionName=lambda_name, WaiterConfig={"Delay": 5, "MaxAttempts": 60})

            # Get the new version number from the response
            new_version = response["Version"]

            logger.info(
                "Updating alias to new version",
                extra={"lambda_name": lambda_name, "alias": "live", "version": new_version},
            )

            try:
                # Try to update the alias
                self.lambda_client.update_alias(FunctionName=lambda_name, Name="live", FunctionVersion=new_version)
            except self.lambda_client.exceptions.ResourceNotFoundException:
                # If alias doesn't exist, create it
                logger.info("Alias 'live' not found, creating", extra={"lambda_name": lambda_name})
                self.lambda_client.create_alias(
                    FunctionName=lambda_name,
                    Name="live",
                    FunctionVersion=new_version,
                    Description="Production alias for the skill",
                )

            return response

        except Exception as e:
            logger.error("Error updating Lambda function %s: %s", lambda_name, str(e), exc_info=True)
            raise

    def update_agent_action_group(
        self,
        agent_external_id: str,
        action_group_name: str,
        lambda_arn: str,
        agent_version: str,
        action_group_id: str,
        function_schema: List[Dict],
        action_group_state: str = "ENABLED",
    ):
        """
        Updates an existing action group for an agent.
        """
        logger.debug("Schema update", extra={"function_count": len(function_schema) if function_schema else 0})
        response = self.bedrock_agent.update_agent_action_group(
            actionGroupExecutor={"lambda": lambda_arn},
            actionGroupName=action_group_name,
            agentId=agent_external_id,
            actionGroupId=action_group_id,
            actionGroupState=action_group_state,
            agentVersion="DRAFT",
            functionSchema={"functions": function_schema},
        )
        return response

    def _create_lambda_iam_role(
        self,
        agent_name: str,
    ) -> object:
        # TODO: use default role for lambda functions
        _lambda_function_role_name = f"{agent_name}-lambda-role-{self._suffix}"
        try:
            _assume_role_policy_document = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "bedrock:InvokeModel",  # noqa
                        "Principal": {"Service": "lambda.amazonaws.com"},
                        "Action": "sts:AssumeRole",  # noqa
                    }
                ],
            }

            _lambda_iam_role = self.iam_client.create_role(
                RoleName=_lambda_function_role_name,
                AssumeRolePolicyDocument=json.dumps(_assume_role_policy_document),
            )

            time.sleep(10)
        except:  # noqa
            _lambda_iam_role = self.iam_client.get_role(RoleName=_lambda_function_role_name)

        self.iam_client.attach_role_policy(
            RoleName=_lambda_function_role_name,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
        )

        return _lambda_iam_role["Role"]["Arn"]

    def upload_inline_traces(self, data, key):
        custom_bucket = os.getenv("AWS_BEDROCK_INLINE_TRACES_BUCKET")
        custom_region = os.getenv("AWS_BEDROCK_INLINE_TRACES_REGION")

        custom_s3_client = boto3.client("s3", region_name=custom_region)

        bytes_stream = BytesIO(data.encode("utf-8"))
        custom_s3_client.upload_fileobj(
            bytes_stream,
            custom_bucket,
            key,
        )

    def upload_traces(self, data, key):
        bytes_stream = BytesIO(data.encode("utf-8"))
        self.s3_client.upload_fileobj(bytes_stream, self.bucket_name, key)

    def get_trace_file(self, key):
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            return response["Body"].read().decode("utf-8")
        except self.s3_client.exceptions.NoSuchKey:
            return []

    def get_inline_trace_file(self, key):
        try:
            custom_bucket = os.getenv("AWS_BEDROCK_INLINE_TRACES_BUCKET")
            custom_region = os.getenv("AWS_BEDROCK_INLINE_TRACES_REGION")

            custom_s3_client = boto3.client("s3", region_name=custom_region)
            response = custom_s3_client.get_object(Bucket=custom_bucket, Key=key)
            return response["Body"].read().decode("utf-8")
        except custom_s3_client.exceptions.NoSuchKey:
            return []

    def get_function(self, function_name: str, version: str = "$LATEST") -> Dict:
        response = self.lambda_client.get_function(FunctionName=function_name, Qualifier=version)
        return response

    def update_agent_instructions(self, agent_id: str, instructions: str):
        """Updates only the agent's instructions field"""
        bedrock_agent = self.get_agent(agent_id)
        agent_details = bedrock_agent.get("agent")

        # Only include required fields and the new instructions
        update_params = {
            "agentId": agent_id,
            "agentName": agent_details["agentName"],
            "agentResourceRoleArn": agent_details["agentResourceRoleArn"],
            "foundationModel": agent_details["foundationModel"],
            "instruction": instructions,
        }

        # Preserve existing agent collaboration if present
        if "agentCollaboration" in agent_details:
            update_params["agentCollaboration"] = agent_details["agentCollaboration"]

        response = self.bedrock_agent.update_agent(**update_params)
        time.sleep(3)
        return response

    def delete_agent_action_group(self, agent_id: str, agent_version: str, action_group_id: str) -> None:
        """Deletes an action group from an agent"""
        try:
            self.bedrock_agent.delete_agent_action_group(
                agentId=agent_id, agentVersion=agent_version, actionGroupId=action_group_id
            )
            logger.info("Successfully deleted action group", extra={"action_group_id": action_group_id})
        except self.bedrock_agent.exceptions.ResourceNotFoundException:
            logger.warning("Action group not found", extra={"action_group_id": action_group_id})
        except Exception as e:
            logger.error("Error deleting action group: %s", e, exc_info=True)
            raise

    def delete_lambda_function(self, function_name: str):
        """Delete Lambda function and all its aliases"""
        try:
            # List and delete all aliases first
            list_aliases = self.lambda_client.list_aliases(FunctionName=function_name)
            aliases = list_aliases.get("Aliases", [])

            for alias in aliases:
                try:
                    self.lambda_client.delete_alias(FunctionName=function_name, Name=alias.get("Name"))
                    logger.info(f"Deleted Lambda alias: {alias.get('Name')}")
                except Exception as e:
                    logger.warning(f"Failed to delete alias {alias.get('Name')}: {e}")

            # Delete the function itself
            self.lambda_client.delete_function(FunctionName=function_name)
            logger.info(f"Successfully deleted Lambda: {function_name}")
        except self.lambda_client.exceptions.ResourceNotFoundException:
            logger.warning(f"Lambda {function_name} not found - already deleted")
        except Exception as e:
            logger.error(f"Error deleting Lambda {function_name}: {e}")
            raise

    def list_agent_action_groups(self, agent_id: str, agent_version: str) -> Dict:
        try:
            response = self.bedrock_agent.list_agent_action_groups(agentId=agent_id, agentVersion=agent_version)
            return response
        except Exception as e:
            logger.error("Error listing action groups: %s", e, exc_info=True)
            raise
