import json
import logging
from typing import Dict, List, Optional, Tuple

import boto3
import requests
import sentry_sdk
import tiktoken
from django.conf import settings

from nexus.intelligences.llms.client import LLMClient
from nexus.intelligences.llms.exceptions import (
    TokenLimitError,
    WeniGPTInvalidVersionError,
)
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
from router.entities import ContactMessageDTO, LLMSetupDTO

logger = logging.getLogger(__name__)


def count_tokens(text: str, encoding_name: str) -> int:
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(text))
    return num_tokens


class WeniGPTClient(LLMClient):
    code = "wenigpt"
    versions = settings.WENIGPT_VERSIONS

    def __init__(self, model_version: str, **kwargs):
        self.validate_version(model_version)

        self.url = self.get_url(model_version)
        self.token = settings.WENIGPT_API_TOKEN
        self.cookie = settings.WENIGPT_COOKIE
        self.api_key = settings.WENIGPT_OPENAI_TOKEN

        self.model_version = model_version

        (
            self.prompt_with_context,
            self.pairs_template_prompt,
            self.next_question_template_prompt,
        ) = self.get_version_prompt(version=model_version, context=True)
        (
            self.prompt_without_context,
            self.pairs_template_prompt,
            self.next_question_template_prompt,
        ) = self.get_version_prompt(version=model_version, context=False)

        self.fine_tunning_models = settings.WENIGPT_FINE_TUNNING_VERSIONS  # deprecated

        self.fine_tunning_prompt_with_context = settings.CHATGPT_CONTEXT_PROMPT
        self.fine_tunning_prompt_without_context = settings.CHATGPT_NO_CONTEXT_PROMPT

        self.few_shot = settings.FEW_SHOT_BOTO
        self.post_prompt = settings.WENIGPT_POST_PROMPT

        self.headers = self._get_headers()

        self.encoding_name: str = settings.SHARK_MODEL_ENCODING_NAME
        self.token_limit: int = settings.SHARK_MODEL_TOKEN_LIMIT

        self.custom_model_id = settings.WENIGPT_BEDROCK_CONVERSATION_CUSTOM_MODEL_ID
        self.bedrock_converse_prompt = settings.BEDROCK_CONVERSE_PROMPT

    def _get_headers(self):
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}", "Cookie": self.cookie}

    def validate_version(self, version: str) -> None:
        if version not in self.versions.keys():
            raise WeniGPTInvalidVersionError(f"WeniGPT {version} is not a valid version")
        return

    def get_url(self, version: str) -> str:
        return self.versions.get(version).get("url")

    def get_version_prompt(self, version: str, context: bool) -> Tuple[str, str, str]:
        prompt = ""
        pairs_template_prompt: str = self.versions.get(version).get("pairs_template_prompt")
        next_question_template_prompt: str = self.versions.get(version).get("next_question_template_prompt")

        if context:
            prompt: str = self.versions.get(version).get("context_prompt")
        else:
            prompt: str = self.versions.get(version).get("no_context_prompt")
        return (prompt, pairs_template_prompt, next_question_template_prompt)

    def format_prompt(
        self, instructions: List, chunks: List, agent: Dict, question: str = "", last_messages: Optional[List] = None
    ) -> str:
        if last_messages is None:
            last_messages = []
        conversation_prompt = ""
        instructions_formatted = "\n".join([f"- {instruction}" for instruction in instructions])
        context = "\n".join([chunk for chunk in chunks])
        prompt = self.get_prompt(instructions_formatted, context, agent, question)

        if self.pairs_template_prompt != '""' and self.next_question_template_prompt != '""':
            for message in last_messages:
                pairs_template = self.pairs_template_prompt
                pairs_template = pairs_template.replace("{{msg_question}}", message.text)
                conversation_prompt += pairs_template.replace("{{msg_answer}}", message.llm_respose)

            next_question_template = self.next_question_template_prompt.replace("{{question}}", question)
            prompt += conversation_prompt + next_question_template
        return prompt.replace("\\n", "\n")

    def validate_prompt(
        self, instructions, chunks, agent, question, last_messages, retry: bool = True
    ) -> Tuple[bool, str]:
        prompt = self.format_prompt(instructions, chunks, agent, question, last_messages)

        is_valid = count_tokens(prompt, self.encoding_name) < self.token_limit

        if not is_valid and retry:
            is_valid, prompt = self.validate_prompt(instructions, chunks[:2], agent, question, last_messages, False)
            return is_valid, prompt

        return is_valid, prompt

    def request_runpod(
        self,
        instructions: List,
        chunks: List,
        agent: Dict,
        question: str,
        llm_config: LLMSetupDTO,
        last_messages: Optional[List[ContactMessageDTO]] = None,
    ):
        if last_messages is None:
            last_messages = []
        is_valid, self.prompt = self.validate_prompt(instructions, chunks, agent, question, last_messages)

        if is_valid:
            data = {
                "input": {
                    "prompt": self.prompt,
                    "sampling_params": {
                        "max_tokens": int(llm_config.max_length)
                        if isinstance(llm_config.max_length, int)
                        else int(settings.WENIGPT_MAX_LENGHT),
                        "top_p": float(settings.WENIGPT_TOP_P),
                        "top_k": int(settings.WENIGPT_TOP_K),
                        "temperature": float(settings.WENIGPT_TEMPERATURE),
                        "stop": settings.WENIGPT_STOP,
                    },
                }
            }

            if settings.TOKEN_LIMIT:
                data.get("input").get("sampling_params").update({"max_tokens": settings.TOKEN_LIMIT})

            text_answers = None

            try:
                logger.debug("Request for WeniGPT", extra={"prompt_len": len(self.prompt) if self.prompt else 0})
                response = requests.request("POST", self.url, headers=self.headers, data=json.dumps(data))
                response_json = response.json()
                logger.debug("WeniGPT JSON response", extra={"keys": list(response_json.keys())})
                text_answers = response_json["output"][0].get("choices")[0].get("tokens")[0]

                return {
                    "answers": [{"text": text_answers}],
                    "id": "0",
                }

            except Exception as e:
                response = {"error": str(e)}
                return {"answers": None, "id": "0", "message": response.get("error")}

        raise TokenLimitError

    def request_gpt(
        self,
        instructions: List,
        chunks: List,
        agent: Dict,
        question: str,
        llm_config: LLMSetupDTO,
        last_messages: Optional[List[ContactMessageDTO]] = None,
        project_uuid: str = "",
    ):
        if last_messages is None:
            last_messages = []
        if settings.USE_BEDROCK_CONVERSE:
            return self.request_bedrock_converse(instructions, chunks, agent, question, last_messages, project_uuid)

        if self.model_version in self.fine_tunning_models:
            self.client = self.get_client()

            self.prompt_with_context = self.fine_tunning_prompt_with_context
            self.prompt_without_context = self.fine_tunning_prompt_without_context

            return self.chat_completion(
                instructions=instructions,
                chunks=chunks,
                agent=agent,
                question=question,
                llm_config=llm_config,
                few_shot=self.few_shot,
                last_messages=last_messages,
            )

        elif settings.USE_BEDROCK_WENIGPT:
            return self.request_bedrock(instructions, chunks, agent, question, last_messages=last_messages)

        return self.request_runpod(instructions, chunks, agent, question, llm_config, last_messages=last_messages)

    def request_bedrock(self, instructions, chunks, agent, question, last_messages):
        try:
            config_data = {
                "max_tokens": int(settings.WENIGPT_MAX_LENGHT),
                "top_p": float(settings.WENIGPT_TOP_P),
                "top_k": float(settings.WENIGPT_TOP_K),
                "stop": settings.WENIGPT_STOP,
                "temperature": float(settings.WENIGPT_TEMPERATURE),
            }

            self.prompt = self.format_prompt(instructions, chunks, agent, question, last_messages)

            bedrock = BedrockFileDatabase()
            response = bedrock.invoke_model(self.prompt, config_data)

            text_answers = json.loads(response["body"].read().decode("utf-8"))

            if text_answers.get("outputs"):
                text_answers = text_answers.get("outputs")[0].get("text")

            return {
                "answers": [{"text": text_answers}],
                "id": "0",
            }
        except Exception as e:
            response = {"error": str(e)}
            return {"answers": None, "id": "0", "message": response.get("error")}

    def format_system_prompt_converse(self, instructions, chunks, agent, question, last_messages):
        has_context = bool(chunks)

        instructions_formatted = "\n".join([f"- {instruction}" for instruction in instructions])
        context = "\n".join([chunk for chunk in chunks])

        context_statement = {
            True: "Na sua memória você tem esse contexto:\\n{{context}}",
            False: "Você não possui conhecimento externo sobre a pergunta do usuário.",
        }

        prompt = self.bedrock_converse_prompt

        prompt = prompt.replace("{{agent_name}}", agent.get("name"))
        prompt = prompt.replace("{{agent_role}}", agent.get("role"))
        prompt = prompt.replace("{{agent_goal}}", agent.get("goal"))
        prompt = prompt.replace("{{agent_personality}}", agent.get("personality"))
        prompt = prompt.replace("{{instructions_formatted}}", instructions_formatted)

        prompt = prompt.replace("{{context_statement}}", context_statement.get(has_context))
        prompt = prompt.replace("{{context}}", context)

        return prompt

    def request_bedrock_converse(self, instructions, chunks, agent, question, last_messages, project_uuid):
        bedrock_client = boto3.client("bedrock-runtime", region_name="us-west-2")
        system_prompt = self.format_system_prompt_converse(instructions, chunks, agent, question, last_messages)
        is_valid = count_tokens(system_prompt, self.encoding_name) < self.token_limit
        self.prompt = system_prompt

        if not is_valid:
            system_prompt = self.format_system_prompt_converse(instructions, chunks[:2], agent, question, last_messages)
            is_valid = count_tokens(system_prompt, self.encoding_name) < self.token_limit
            self.prompt = system_prompt

        if is_valid:
            system_config = [{"text": system_prompt}]
            conversation_history = []

            for message in last_messages:
                conversation_history += [
                    {"role": "user", "content": [{"text": message.text}]},
                    {"role": "assistant", "content": [{"text": message.llm_respose}]},
                ]

            conversation = [{"role": "user", "content": [{"text": question}]}]

            conversation_history += conversation

            inference_config = {
                "maxTokens": settings.BEDROCK_CONVERSE_MAX_LENGHT,
                "temperature": float(settings.WENIGPT_TEMPERATURE),
                "topP": float(settings.WENIGPT_TOP_P),
            }

            try:
                response = bedrock_client.converse(
                    modelId=self.custom_model_id,
                    messages=conversation_history,
                    system=system_config,
                    inferenceConfig=inference_config,
                )
                if response["ResponseMetadata"]["HTTPStatusCode"] != 200:
                    raise Exception("Error on Bedrock converse")

                response_text = response.get("output", {}).get("message", {}).get("content", [{}])[0].get("text")

                return {
                    "answers": [{"text": response_text}],
                    "id": "0",
                }
            except Exception as e:
                sentry_sdk.set_context("question", question)
                sentry_sdk.set_tag("project_uuid", project_uuid)
                sentry_sdk.capture_exception(e)
                logger.error(f"Error on Bedrock converse: {str(e)}")
                response = {"error": str(e)}
                return {"answers": [{"text": ""}], "id": "0", "message": response.get("error")}

        raise TokenLimitError
