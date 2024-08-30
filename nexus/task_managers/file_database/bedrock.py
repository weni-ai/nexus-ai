import uuid
import json
import boto3
from os.path import basename
from django.conf import settings

from .file_database import FileDataBase, FileResponseDTO


class BedrockFileDatabase(FileDataBase):
    def __init__(self) -> None:
        self.data_source_id = settings.AWS_BEDROCK_DATASOURCE_ID
        self.knowledge_base_id = settings.AWS_BEDROCK_KNOWLEDGE_BASE_ID
        self.region_name = settings.AWS_BEDROCK_REGION_NAME
        self.bucket_name = settings.AWS_BEDROCK_BUCKET_NAME
        self.access_key = settings.AWS_BEDROCK_ACCESS_KEY
        self.secret_key = settings.AWS_BEDROCK_SECRET_KEY

        self.s3_client = self.__get_s3_client()
        self.bedrock_agent = self.__get_bedrock_agent()
        self.bedrock_agent_runtime = self.__get_bedrock_agent_runtime()

    def add_metadata_json_file(self, filename, content_base_uuid: str, file_uuid: str):
        print("[+ Adding metadata.json file +]")

        data = {
            "metadataAttributes": {
                "contentBaseUuid": content_base_uuid,
                "filename": filename,
                "fileUuid": file_uuid
            }
        }

        filename_metadata_json = f"{filename}.metadata.json"
        file_path = f"/tmp/{filename_metadata_json}"

        with open(file_path, "w") as file:
            file.write(json.dumps(data))

        with open(file_path, "rb") as file:
            self.s3_client.upload_fileobj(file, self.bucket_name, f"{content_base_uuid}/{filename_metadata_json}")

    def add_file(self, file, content_base_uuid: str, file_uuid: str) -> FileResponseDTO:
        try:
            print("[+ Adding file to bedrock bucket +]")

            file_name = self.__create_unique_filename(basename(file.name))
            response = FileResponseDTO()

            file_path = f"{content_base_uuid}/{file_name}"

            response.status = 0
            response.file_url = f"https://{self.bucket_name}.s3.{self.region_name}.amazonaws.com/{file_path}"
            response.file_name = file_name

            self.s3_client.upload_fileobj(file, self.bucket_name, file_path)
            self.add_metadata_json_file(file_name, content_base_uuid, file_uuid)

        except ZeroDivisionError as exception:
            response.status = 1
            response.err = str(exception)

        return response

    def delete_file_and_metadata(self, content_base_uuid: str, filename: str):
        file = f"{content_base_uuid}/{filename}"
        response_file = self.s3_client.delete_object(
            Bucket=self.bucket_name,
            Key=file,
        )

        file_metadata = f"{content_base_uuid}/{filename}.metadata.json"
        response_metadata = self.s3_client.delete_object(
            Bucket=self.bucket_name,
            Key=file_metadata,
        )

        file_status = response_file.get("DeleteMarker")
        metadata_status = response_metadata.get("DeleteMarker")

        if file_status and metadata_status:
            return True

        raise Exception

    def start_bedrock_ingestion(self) -> str:
        print("[+ Starting ingestion job +]")
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

    def list_bedrock_ingestion(self):
        response = self.bedrock_agent.list_ingestion_jobs(
            dataSourceId=self.data_source_id,
            knowledgeBaseId=self.knowledge_base_id,
            filters=[
                {
                    'attribute': 'STATUS',
                    'operator': 'EQ',
                    'values': [
                        'STARTING',
                        'IN_PROGRESS'
                    ]
                },
            ]
        )
        return response.get("ingestionJobSummaries")

    def search_data(self, content_base_uuid: str, text: str, number_of_results: int = 5):
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
        llm_chunk_list = []
        chunks = response.get("retrievalResults")

        for chunk in chunks:
            llm_chunk_list.append(
                {
                    "full_page": chunk.get("content").get("text"),
                    "filename": chunk.get("metadata").get("filename"),
                    "file_uuid": chunk.get("metadata").get("fileUuid"),
                }
            )

        data = {
            "response": llm_chunk_list
        }
        return {
            "status": response.get("ResponseMetadata").get("HTTPStatusCode"),
            "data": data
        }

    def create_presigned_url(self, file_name: str, expiration: int = 3600) -> str:
        pass

    def __create_unique_filename(self, filename: str) -> str:
        name, extension = filename.rsplit(".", 1)
        name = name.replace(".", "_")
        filename = f"{name}-{uuid.uuid4()}.{extension}"
        return filename

    def __get_s3_client(self):
        return boto3.client(
            "s3",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_name
        )

    def __get_bedrock_agent(self):
        return boto3.client(
            "bedrock-agent",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_name
        )

    def __get_bedrock_agent_runtime(self):
        return boto3.client(
            "bedrock-agent-runtime",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_name
        )
