import json
import requests

from django.conf import settings
from typing import List
from nexus.usecases.task_managers.wenigpt_database import get_prompt_by_language
from nexus.usecases.intelligences.intelligences_dto import ContentBaseLogsDTO
from nexus.task_managers.file_database import GPTDatabase

class WeniGPTDatabase(GPTDatabase):

    def __init__(self):
        self.url = settings.WENIGPT_API_URL
        self.token = settings.WENIGPT_API_TOKEN
        self.cookie = settings.WENIGPT_COOKIE

    def request_gpt(self, contexts: List, question: str, language: str, content_base_uuid: str, testing: bool = False):
        from nexus.task_managers.tasks import create_wenigpt_logs
        if contexts:
            context = "\n".join([str(ctx) for ctx in contexts])
            base_prompt = get_prompt_by_language(language=language, context=context, question=question)
            print("[+]WeniGPT[+]")
            print(base_prompt)
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
                "Cookie": self.cookie
            }
            data = {
                "input": {
                    "prompt": base_prompt,
                    "sampling_params": {
                        "max_new_tokens": settings.WENIGPT_MAX_NEW_TOKENS,
                        "max_length": settings.WENIGPT_MAX_LENGHT,
                        "top_p": settings.WENIGPT_TOP_P,
                        "top_k": settings.WENIGPT_TOP_K,
                        "temperature": settings.WENIGPT_TEMPERATURE,
                        "do_sample": False,
                        "stop": settings.WENIGPT_STOP,
                    }
                }
            }

            text_answers = None
            try:
                response = requests.request("POST", self.url, headers=headers, data=json.dumps(data))
                response_json = response.json()
                text_answers = response_json["output"].get("text")
                log_dto = ContentBaseLogsDTO(
                    content_base_uuid=content_base_uuid,
                    question=question,
                    language=language,
                    texts_chunks=contexts,
                    full_prompt=base_prompt,
                    weni_gpt_response=text_answers,
                    testing=testing
                )
                log = create_wenigpt_logs(log_dto.__dict__)
                return {
                    "answers": self.format_output(text_answers),
                    "id": "0",
                    "question_uuid": str(log.user_question.uuid)
                }

            except Exception as e:
                response = {"error": str(e)}
                print(response)

        return {"answers": None, "id": "0", "message": "No context found for this question"}
