import re
import pendulum

from typing import Dict
from router.classifiers.interfaces import OpenAIClientInterface
from openai import OpenAI

from django.conf import settings

from nexus.logs.models import MessageLog


class OpenAIClient(OpenAIClientInterface):  # pragma: no cover

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = OpenAI(api_key=self.api_key)

    def chat_completions_create(
        self,
        messages,
    ):
        groundedness_model = settings.GROUNDEDNESS_MODEL
        return self.client.chat.completions.create(
            model=groundedness_model,
            messages=messages,
        )


class Groundedness:

    def __init__(
        self,
        llm_response: str,
        llm_chunk_used: str,
        log: MessageLog,
        system_prompt: str = settings.GROUNDEDNESS_SYSTEM_PROMPT,
        user_prompt: str = settings.GROUNDEDNESS_USER_PROMPT,
        score_avg_threshold: int = settings.GROUNDEDNESS_SCORE_AVG_THRESHOLD,
    ) -> None:

        self.client = OpenAIClient(settings.OPENAI_API_KEY)
        self.llm_chunk_used = llm_chunk_used
        self.llm_response = llm_response
        self.log = log
        self.system_prompt = system_prompt.replace("\\n", "\n")
        self.user_prompt = user_prompt.replace("\\n", "\n")
        self.score_avg_threshold = score_avg_threshold

    def extract_score_and_sentences(
        self,
        response: str
    ):
        pattern = re.compile(
            r"Statement Sentence: (?P<sentence>.*?),\s*Supporting Evidence:\s*(?P<evidence>.*?)(?:,|\s*)\s*Score:\s*(?P<score>\d+)"
        )
        matches = pattern.findall(response)

        result = []
        for match in matches:
            result.append({
                "sentence": match[0],
                "evidence": match[1],
                "score": match[2]
            })

        return result

    def replace_vars(self, prompt: str, replace_variables: Dict) -> str:
        for key in replace_variables.keys():
            replace_str = "{{" + key + "}}"
            value = replace_variables.get(key)
            if not isinstance(value, str):
                value = str(value)
            prompt = prompt.replace(replace_str, value)
        return prompt

    def get_prompt(self):
        variable = {
            "premise": "".join(self.llm_chunk_used),
            "hypothesis": self.llm_response,
        }

        return self.replace_vars(
            prompt=self.user_prompt,
            replace_variables=variable
        )

    def classify(self):

        started_groundedness = pendulum.now()

        formated_prompt = self.get_prompt()

        gpt_response = self.client.chat_completions_create(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": formated_prompt},
            ],
        )

        response_content = gpt_response.choices[0].message.content
        groundedness_values = self.extract_score_and_sentences(response_content)

        if not groundedness_values:
            return None

        score_avg = sum([int(item["score"]) for item in groundedness_values]) / len(groundedness_values)
        tag = "answer_valid" if self.score_avg_threshold < 8 else "answer_not_valid"
        finished_groundedness = pendulum.now()

        usage_time = finished_groundedness.diff(started_groundedness).in_seconds()

        self.log.reflection_data = {
            "tag": tag,
            "request_time": usage_time,
            "sentence_rankings": response_content
        }

        self.log.groundedness_score = score_avg
        self.log.save()

        return gpt_response
