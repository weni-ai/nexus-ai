from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.task_managers.file_database.wenigpt_database import WeniGPTDatabase


class IntelligenceGenerativeSearchUseCase():

    def search(self, content_base_uuid: str, text: str):
        print(f"[IntelligenceGenerativeSearchUseCase] {content_base_uuid} {text}")
        response = SentenXFileDataBase().search_data(content_base_uuid, text)
        print(f"[IntelligenceGenerativeSearchUseCase] {response}")
        if response.get("status") != 200:
            raise Exception(response.get("data"))
        wenigpt_database = WeniGPTDatabase()
        return wenigpt_database.request_wenigpt(contexts=response.get("data", []), question=text)
