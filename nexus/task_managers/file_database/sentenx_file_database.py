import requests
from django.conf import settings

from nexus.task_managers.models import TaskManager


class SentenXFileDataBase:
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": f"Bearer {settings.SENTENX_AUTH_TOKEN}",
        }

    def add_file(self, task: TaskManager):
        url = settings.SENTENX_BASE_URL + "/content_base/index"

        body = {
            "file": task.content_base_file.file,
            "filename": task.content_base_file.file_name,
            "extension_file": task.content_base_file.extension_file,
            "task_uuid": str(task.uuid),
            "content_base": str(task.content_base_file.content_base.uuid)
        }
        response = requests.post(url=url, headers=self.headers, json=body)

        if response.status_code == 200:
            return response.status_code, response.json()

        return response.status_code, response.text

    def add_text_file(self, task: TaskManager):
        url = settings.SENTENX_BASE_URL + "/content_base/index"

        body = {
            "file": task.file_url,
            "filename": task.file_name,
            "extension_file": 'txt',
            "task_uuid": str(task.uuid),
            "content_base": str(task.content_base_text.content_base.uuid)
        }
        response = requests.post(url=url, headers=self.headers, json=body)

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
