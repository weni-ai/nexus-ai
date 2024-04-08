import json
from typing import List, Dict

import requests

from django.conf import settings

from nexus.intelligences.llms.client import LLMClient
from nexus.task_managers.tasks import create_wenigpt_logs
from nexus.usecases.intelligences.intelligences_dto import ContentBaseLogsDTO


class WeniGPTClient(LLMClient):
    code = "wenipgt"
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.chatgpt_model = settings.CHATGPT_MODEL
        self.headers = self._get_headers()

    def _get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Cookie": self.cookie
        }

    def format_prompt(self, instructions: List, chunks: List, agent: Dict, question: str):
        instructions_formatted = "\n".join([f"- {instruction}" for instruction in instructions])
        context = "\n".join([chunk for chunk in chunks])
        prompt = f"""
        Agora você se chama {agent.get('name')}, você é {agent.get('role')} e seu objetivo é {agent.get('goal')}. O adjetivo que mais define a sua personalidade é {agent.get('personality')} e você se comporta da seguinte forma:
        {instructions_formatted}
        Na sua memória você tem esse contexto:
        {context}
        Lista de requisitos:
        - Responda de forma natural, mas nunca fale sobre um assunto fora do contexto.
        - Nunca traga informações do seu próprio conhecimento.
        - Repito é crucial que você responda usando apenas informações do contexto.
        - Nunca mencione o contexto fornecido.
        - Nunca mencione a pergunta fornecida.
        - Gere a resposta mais útil possível para a pergunta usando informações do conexto acima.
        - Nunca elabore sobre o porque e como você fez a tarefa, apenas responda.

        {question}
        """
        return prompt

    def request_gpt(self, instructions: List, chunks: List, agent: Dict, question: str, llm_config):
        prompt = self.format_prompt(instructions, chunks, agent, question)
        data = {
            "input": {
                "prompt": prompt,
                "sampling_params": {
                    "max_new_tokens": settings.WENIGPT_MAX_NEW_TOKENS,
                    "max_length": llm_config.setup.get("max_length", settings.WENIGPT_MAX_LENGHT),
                    "top_p": llm_config.setup.get("top_p", settings.WENIGPT_TOP_P),
                    "top_k": llm_config.setup.get("top_k", settings.WENIGPT_TOP_K),
                    "temperature": llm_config.setup.get("temperature", settings.WENIGPT_TEMPERATURE),
                    "do_sample": False,
                    "stop": settings.WENIGPT_STOP,
                }
            }
        }

        text_answers = None

        try:
            response = requests.request("POST", self.url, headers=self.headers, data=json.dumps(data))
            response_json = response.json()
            text_answers = response_json["output"].get("text")

            # log_dto = ContentBaseLogsDTO(
            #     content_base_uuid=content_base_uuid,
            #     question=question,
            #     language=language,
            #     texts_chunks=contexts,
            #     full_prompt=base_prompt,
            #     weni_gpt_response=text_answers,
            #     testing=testing
            # )
            # log = create_wenigpt_logs(log_dto.__dict__)

            return {
                "answers": self.format_output(text_answers),
                "id": "0",
                # "question_uuid": str(log.user_question.uuid)
            }

        except Exception as e:
            response = {"error": str(e)}
            print(response)
            return {"answers": None, "id": "0", "message": response.get("error")}

        # return {"answers": None, "id": "0", "message": "No context found for this question"}
