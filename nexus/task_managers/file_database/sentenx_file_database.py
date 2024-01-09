import requests
from django.conf import settings

from nexus.task_managers.models import TaskManager


class SentenXFileDataBase:

    def add_file(self, task: TaskManager):
        url = settings.SENTENX_BASE_URL + "/content_base/index"
        headers = {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": f"Bearer {settings.SENTENX_AUTH_TOKEN}",
        }
        body = {
            "file": task.content_base_file.file,
            "filename": task.content_base_file.file_name,
            "extension_file": task.content_base_file.extension_file,
            "task_uuid": str(task.uuid),
            "content_base": str(task.content_base_file.content_base.uuid)
        }
        response = requests.post(url=url, headers=headers, json=body)

        if response.status_code == 200:
            return response.status_code, response.json()

        return response.status_code, response.text


    def search_data(self, content_base_uuid: str, text: str):
        url = settings.SENTENX_BASE_URL + "/content_base/search"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.SENTENX_AUTH_TOKEN}",
        }
        body = {
            "search": text,
            "filter": {
                "content_base_uuid": content_base_uuid
            },
        }
        response = requests.post(url=url, headers=headers, json=body)
        return {"status": response.status_code, "data": response.json() if response.status_code == 200 else response.text}