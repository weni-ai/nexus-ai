import requests
from django.conf import settings

from nexus.task_managers.models import TaskManager
from .file_database import FileDataBase


class SentenXFileDataBase:
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": f"Bearer {settings.SENTENX_AUTH_TOKEN}",
        }

    def add_file(self, task: TaskManager, file_database: FileDataBase, load_type: str):
        url = settings.SENTENX_BASE_URL + "/content_base/index"
        body = {
            "file": file_database.create_presigned_url(task.content_base_file.file_name),
            "filename": task.content_base_file.file_name,
            "file_uuid": str(task.content_base_file.uuid),
            "extension_file": task.content_base_file.extension_file,
            "task_uuid": str(task.uuid),
            "content_base": str(task.content_base_file.content_base.uuid),
            "load_type": load_type
        }
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
        print(f"BODY: {body}")
        response = requests.put(url=url, headers=self.headers, json=body)

        if response.status_code == 200:
            return response.status_code, response.json()
        return response.status_code, response.text

    def search_data(self, content_base_uuid: str, text: str):
        url = settings.SENTENX_BASE_URL + "/content_base/search"

        body = {
            "search": text,
            "filter": {
                "content_base_uuid": content_base_uuid
            },
        }

        response = requests.post(url=url, headers=self.headers, json=body)

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
