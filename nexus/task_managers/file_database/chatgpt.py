from typing import List
from openai import OpenAI
from django.conf import settings

from nexus.task_managers.file_database import GPTDatabase
from nexus.usecases.task_managers.wenigpt_database import get_prompt_by_language


class ChatGPTDatabase(GPTDatabase):

    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.chatgpt_model = settings.CHATGPT_MODEL
        self.client = self.get_client()

    def get_client(self):
        return OpenAI(api_key=self.api_key)
    
    def request_gpt(self, contexts: List, question: str, language: str, content_base_uuid: str):
        if not contexts:
            return {"answers": None, "id": "0", "message": "No context found for this question"}

        context = "\n".join([str(ctx) for ctx in contexts])
        base_prompt = get_prompt_by_language(language=language, context=context, question=question)

        chat_completion = self.client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": base_prompt
                }
            ],
            model=settings.CHATGPT_MODEL
        )
        text_answers = chat_completion.choices[0].message.content
        return {"answers":[{"text": text_answers}],"id":"0"}
