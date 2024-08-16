import uuid
import boto3
import json

from os.path import basename
from django.conf import settings
from typing import Tuple
from .file_database import FileDataBase, FileResponseDTO
from nexus.usecases.intelligences.intelligences_dto import ContentBaseFileDTO
from nexus.events import event_manager


class BedrockDatabase(FileDataBase):
    def __init__(self, event_manager_notify=event_manager.notify) -> None:
        self.s3_client = self.__get_s3_client()
        self.bedrock_agent = self.__get_bedrock_agent()
        self.bedrock_agent_runtime = self.__get_bedrock_agent_runtime()

        self.data_source_id = settings.AWS_S3_DATASOURCE_ID
        self.knowledgebase_id = settings.AWS_S3_KNOWLEDGEBASE_ID
        self.region_name = settings.AWS_S3_REGION_NAME
        self.bucket_name = settings.AWS_S3_BEDROCK_BUCKET_NAME
        self.event_manager_notify = event_manager_notify

    def get_chunks(
        self,
        query,
        content_base_uuid:str
    ) -> list:

        retrieval_config = {
            "vectorSearchConfiguration": {
                "filter": {
                    "equals": {
                        "key": "contentBaseUuid",
                        "value": str(content_base_uuid)
                    }
                },
                "numberOfResults": 5
            }
        }

        response_chunks = self.bedrock_agent_runtime.retrieve(
            knowledgeBaseId=self.knowledgebase_id,
            retrievalConfiguration=retrieval_config,
            retrievalQuery={
                "text": query
            }
        )

        llm_chunk_list = []
        chunks = response_chunks.get('retrievalResults')

        for chunk in chunks:
            selected_chunk = chunk.get('content').get('text')

            file_source = chunk.get('location').get('s3Location').get('uri')        
            file_name = file_source.split('/')[-1]

            llm_chunk_list.append({(selected_chunk, file_name)})

        return llm_chunk_list

    def bedrock_ingestion(self) -> str:
        response = self.bedrock_agent.start_ingestion_job(
            dataSourceId="123",
            knowledgeBaseId=self.knowledgebase_id
        )

        ingestion_job_id = response.get('ingestionJob').get('ingestionJobId')
        return ingestion_job_id

    def bedrock_ingestion_status(self, ingestionJobId: str):
        response = self.bedrock_agent.get_ingestion_job(
            dataSourceId=self.data_source_id,
            ingestionJobId=ingestionJobId,
            knowledgeBaseId=self.knowledgebase_id
        )
        # status types: 'STARTING'|'IN_PROGRESS'|'COMPLETE'|'FAILED'
        status = response.get('ingestionJob').get('status')
        return status

    def add_metadata_json_file(self, filename: str, content_base_uuid: str, file_uuid: str):
        print("[+ Add metadata to file +]")
        
        data = {
            "metadataAttributes": {
                "contentBaseUuid": content_base_uuid,
                "filename": filename,
                "fileUuid": file_uuid
            }
        }

        filename = f"{filename}.metadata.json"
        file_path = f"/tmp/{filename}"

        with open(file_path, 'w') as file:
            file.write(json.dumps(data))

        with open(file_path, 'rb') as file:
            self.s3_client.upload_fileobj(file, settings.AWS_S3_BUCKET_NAME, f"{content_base_uuid}/{filename}")

    def add_file(self, file, content_base_uuid, file_uuid, task_uuid, file_type) -> FileResponseDTO:
        try:
            print("[+ Add file to bedrock bucket +]")
            file_name = basename(file.name)        
            file_name, extension = self.__clean_file_name(file_name)
            file_name_ext  = f"{file_name}.{extension}"
            
            response = FileResponseDTO()

            self.s3_client.upload_fileobj(file, settings.AWS_S3_BUCKET_NAME, f"{content_base_uuid}/{file_name_ext}")

            response.status = 0
            response.file_url = f"https://{settings.AWS_S3_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{file_name}"
            response.file_name = file_name_ext

            self.add_metadata_json_file(file_name_ext, content_base_uuid, file_uuid)
            self.bedrock_ingestion()

        except Exception as exception:
            response.status = 1
            response.err = str(exception)
            print(exception)

        return response

    def delete_file(self, content_base_uuid: str, filename:str) -> bool:

        response = self.s3_client.delete_object(
            Bucket=self.bucket_name,
            Key=f"{content_base_uuid}/{filename}",
        )

        file_metadata = f"{content_base_uuid}/{filename}.metadata.json"
        
        response = self.s3_client.delete_object(
            Bucket=self.bucket_name,
            Key=file_metadata,
        )
        status = response.get('DeleteMarker')

        if status == False:
            raise Exception

        return status

    def __get_s3_client(self):
        return boto3.client(
            's3',
            aws_access_key_id=settings.AWS_BEDROCK_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_BEDROCK_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )

    def __get_bedrock_agent(self):
        return boto3.client(
            'bedrock-agent',
            aws_access_key_id=settings.AWS_BEDROCK_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_BEDROCK_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )

    def __get_bedrock_agent_runtime(self):
        return boto3.client(
            'bedrock-agent-runtime',
            aws_access_key_id=settings.AWS_BEDROCK_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_BEDROCK_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )

    def __clean_file_name(self, file_name: str) -> Tuple[str, str]:
        name, extension = file_name.rsplit(".", 1)
        name = name.replace(".", "_")
        file_name = f"{name}-{uuid.uuid4()}"
        return file_name, extension


class s3FileDatabase(FileDataBase):
    def __init__(self) -> None:
        self.s3_client = boto3.client(
            's3',
            # aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            # aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )

    def add_file(self, file, **kwargs) -> FileResponseDTO:
        file_name = basename(file.name)
        name, extension = file_name.rsplit(".", 1)
        name = name.replace(".", "_")
        file_name = f"{name}-{uuid.uuid4()}"
        file_name_ext  = f"{file_name}.{extension}"
        response = FileResponseDTO()
        try:
            self.s3_client.upload_fileobj(file, settings.AWS_S3_BUCKET_NAME, file_name_ext)
            response.status = 0
            response.file_url = f"https://{settings.AWS_S3_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{file_name}"
            response.file_name = file_name_ext
            if content_base_file_dto:
                self.add_metadata_json_file(file_name, content_base_file)

        except Exception as exception:
            response.status = 1
            response.err = str(exception)
        return response

    def create_presigned_url(self, file_name: str, expiration: int = 3600) -> str:
        return self.s3_client.generate_presigned_url('get_object', Params={'Bucket': settings.AWS_S3_BUCKET_NAME, 'Key': file_name}, ExpiresIn=expiration)
