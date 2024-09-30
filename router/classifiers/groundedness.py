from typing import Dict
from router.classifiers.interfaces import OpenAIClientInterface

from django.conf import settings


class Groundedness:

    def __init__(
        self,
        client: OpenAIClientInterface,
        llm_response: str,
        llm_chunk_used: str,
        log_usecase,
    ) -> None:
        self.client = client
        self.llm_chunk_used = llm_chunk_used
        self.llm_response = llm_response

        self.system_prompt = (
            """You are a INFORMATION OVERLAP classifier; providing the overlap of information between the source and statement.
            Respond only as a number from 0 to 10 where 0 is no information overlap and 10 is all information is overlapping.
            Never elaborate."""
        )
        self.user_prompt = (
            """
            SOURCE: {{premise}}

            Hypothesis: {{hypothesis}}

            Please answer with the template below for all statement sentences:

            Statement Sentence: <Sentence>,
            Supporting Evidence: <Choose the exact unchanged sentences in the source that can answer the statement, if nothing matches, say NOTHING FOUND>
            Score: <Output a number between 0-10 where 0 is no information overlap and 10 is all information is overlapping>
            """
        )

        self.groundedness_model = settings.GROUNDEDNESS_MODEL
        # self.groundedness_prompt = settings.GROUNDEDNESS_PROMPT

    def replace_vars(self, prompt: str, replace_variables: Dict) -> str:
        for key in replace_variables.keys():
            replace_str = "{{" + key + "}}"
            prompt = prompt.replace(replace_str, replace_variables.get(key))
        return prompt

    def get_prompt(self):
        variable = {
            "premise": self.llm_chunk_used,
            "hypothesis": self.llm_response,
        }

        return self.replace_vars(variable)

    def classify(self):

        formated_prompt = self.get_prompt()
        gpt_response = self.client.chat_completions_create(
            model=self.groundedness_model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": formated_prompt},
            ],
        )


        return False


groundedness = Groundedness(
    client=client,
    llm_response=llm_response,
    llm_chunk_used=llm_chunk_used,
    log_usecase=log_usecase
)