import requests
from django.conf import settings
from abc import ABC

from nexus.task_managers.models import TaskManager
from .file_database import FileDataBase


class SentenXInterface(ABC):

    def __init__(self):
        self.headers = {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": f"Bearer {settings.SENTENX_AUTH_TOKEN}",
        }


class SentenXFileDataBase:
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": f"Bearer {settings.SENTENX_AUTH_TOKEN}",
        }

    def add_file(self, task: TaskManager, file_database: FileDataBase, load_type: str = None):
        url = settings.SENTENX_BASE_URL + "/content_base/index"
        body = {
            "file": file_database.create_presigned_url(task.content_base_file.file_name),
            "filename": task.content_base_file.file_name,
            "file_uuid": str(task.content_base_file.uuid),
            "extension_file": task.content_base_file.extension_file,
            "task_uuid": str(task.uuid),
            "content_base": str(task.content_base_file.content_base.uuid)
        }
        if load_type:
            body.update({"load_type": load_type})
        response = requests.put(url=url, headers=self.headers, json=body)

        if response.status_code == 200:
            return response.status_code, response.json()

        return response.status_code, response.text

    def add_text_file(self, task: TaskManager, file_database: FileDataBase):
        url = settings.SENTENX_BASE_URL + "/content_base/index"
        body = {
            "file": file_database.create_presigned_url(task.content_base_text.file_name),
            "filename": task.content_base_text.file_name,
            "file_uuid": str(task.content_base_text.uuid),
            "extension_file": 'txt',
            "task_uuid": str(task.uuid),
            "content_base": str(task.content_base_text.content_base.uuid)
        }
        response = requests.put(url=url, headers=self.headers, json=body)

        if response.status_code == 200:
            return response.status_code, response.json()

        return response.status_code, response.text

    def add_link(self, task: TaskManager, file_database: FileDataBase):
        url = settings.SENTENX_BASE_URL + "/content_base/index"
        body = {
            "file": task.content_base_link.link,
            "filename": task.content_base_link.link,
            "file_uuid": str(task.content_base_link.uuid),
            "extension_file": 'urls',
            "task_uuid": str(task.uuid),
            "content_base": str(task.content_base_link.content_base.uuid)
        }
        response = requests.put(url=url, headers=self.headers, json=body)

        if response.status_code == 200:
            return response.status_code, response.json()
        return response.status_code, response.text

    def search_data(self, content_base_uuid: str, text: str):
        url = settings.SENTENX_BASE_URL + "/content_base/search"

        body = {
            "search": text,
            "threshold": settings.SENTENX_THRESHOLD,
            "filter": {
                "content_base_uuid": content_base_uuid
            },
        }

        response = requests.post(url=url, headers=self.headers, json=body)
        response.raise_for_status()

        if response.status_code == 200:
            return {
                "status": response.status_code,
                "data": response.json()
            }

        return {
            "status": response.status_code,
            "data": response.text
        }

    def delete(self, content_base_uuid: str, content_base_file_uuid: str, filename: str):
        url = settings.SENTENX_BASE_URL + "/content_base/delete"
        body = {
            "content_base": content_base_uuid,
            "filename": filename,
            "file_uuid": content_base_file_uuid,
        }
        response = requests.delete(url=url, headers=self.headers, json=body)
        if response.status_code == 204:
            return {
                "status": response.status_code,
            }
        return {
            "status": response.status_code,
            "data": response.text
        }


class SentenXDocumentPreview(SentenXInterface):

    def paginate_content(
        self,
        content: list,
        page_size: int,
        page_number: int
    ) -> dict:
        start_index = (page_number - 1) * page_size
        end_index = start_index + page_size
        paginated_content = content[start_index:end_index]

        total_pages = -(-len(content) // page_size)

        return {
            "content": paginated_content,
            "page_number": page_number,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def document_preview(
        self,
        content_base_file_uuid: str,
        content_base_uuid: str,
        page_size: int,
        page_number: int
    ) -> dict:
        url = settings.SENTENX_BASE_URL + "/content_base/search-document"
        body = {
            "file_uuid": content_base_file_uuid,
            "content_base_uuid": content_base_uuid,
        }

        try:

            response = requests.post(url=url, headers=self.headers, json=body)
            response.raise_for_status()

            json_response = response.json()
            content = json_response.get("content")

            if not content:
                return {
                    "status": 404,
                    "data": "Content not found"
                }

            paginated_content = self.paginate_content(
                content=content,
                page_size=page_size,
                page_number=page_number
            )

            return {
                "status": response.status_code,
                "data": paginated_content
            }
        except requests.exceptions.RequestException as e:
            return {"status": 500, "data": str(e)}
