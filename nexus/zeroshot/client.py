import json
from typing import Dict

import boto3
import requests
from django.conf import settings
from nexus.zeroshot.format_classification import FormatClassification
from nexus.zeroshot.format_prompt import FormatPrompt

from router.classifiers.chatgpt_function import ChatGPTFunctionClassifier
from router.entities.flow import FlowDTO


class InvokeModel:
    def __init__(
            self,
            zeroshot_data: Dict,
            model_backend: str = settings.ZEROSHOT_MODEL_BACKEND,
            aws_access_key_id: str = settings.ZEROSHOT_BEDROCK_AWS_KEY,
            aws_secret_access_key: str = settings.ZEROSHOT_BEDROCK_AWS_SECRET,
            region_name: str = settings.ZEROSHOT_BEDROCK_AWS_REGION) -> None:
        self.zeroshot_data = zeroshot_data
        self.model_backend = model_backend
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.region_name = region_name

    def _get_prompt(self, zeroshot_data: Dict):
        prompt_formatter = FormatPrompt()

        language = zeroshot_data.get("language", prompt_formatter.get_default_language())
        return prompt_formatter.generate_prompt(language, zeroshot_data)

    def _invoke_bedrock(self, prompt):
        response = {"output": {}}

        session = boto3.Session(
            aws_access_key_id=settings.ZEROSHOT_BEDROCK_AWS_KEY,
            aws_secret_access_key=settings.ZEROSHOT_BEDROCK_AWS_SECRET,
            region_name=settings.ZEROSHOT_BEDROCK_AWS_REGION
        )

        bedrock_runtime = session.client('bedrock-runtime')
        payload = json.dumps({
            "max_tokens": settings.ZEROSHOT_MAX_TOKENS,
            "top_p": settings.ZEROSHOT_TOP_P,
            "top_k": settings.ZEROSHOT_TOP_K,
            "stop": settings.ZEROSHOT_STOP,
            "temperature": settings.ZEROSHOT_TEMPERATURE,
            "prompt": prompt
        })

        bedrock_response = bedrock_runtime.invoke_model(
            body=payload,
            contentType='application/json',
            accept='application/json',
            modelId=settings.ZEROSHOT_BEDROCK_MODEL_ID,
            trace='ENABLED'
        )

        classification = json.loads(bedrock_response['body'].read().decode('utf-8'))

        classification_formatter = FormatClassification(classification)
        formatted_classification = classification_formatter.get_classification(self.zeroshot_data)

        response["output"] = formatted_classification
        return response

    def _invoke_runpod(self, prompt):
        payload = json.dumps({
            "input": {
                "prompt": prompt,
                "sampling_params": {
                    "max_tokens": settings.ZEROSHOT_MAX_TOKENS,
                    "n": settings.ZEROSHOT_N,
                    "top_p": settings.ZEROSHOT_TOP_P,
                    "top_k": settings.ZEROSHOT_TOP_K,
                    "temperature": settings.ZEROSHOT_TEMPERATURE,
                    "stop": settings.ZEROSHOT_STOP
                }

            }
        })

        headers = {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": f"Bearer {settings.ZEROSHOT_TOKEN}",
        }
        response_nlp = None
        response = {"output": {}}

        url = settings.ZEROSHOT_BASE_NLP_URL
        if len(settings.ZEROSHOT_SUFFIX) > 0:
            url += settings.ZEROSHOT_SUFFIX
        response_nlp = requests.post(
            headers=headers,
            url=url,
            data=payload
        )

        response_nlp.raise_for_status()

        if response_nlp.status_code == 200:
            classification = response_nlp.json()
            classification_formatter = FormatClassification(classification)
            formatted_classification = classification_formatter.get_classification(self.zeroshot_data)

            response["output"] = formatted_classification

        return response

    def _invoke_zeroshot(self, model_backend: str):
        return {
            "runpod": self._invoke_runpod,
            "bedrock": self._invoke_bedrock
        }.get(model_backend)

    def _invoke_function_calling(self):

        classifier = ChatGPTFunctionClassifier(
            agent_goal=self.zeroshot_data.get("context"),
        )

        flow_dto_list = []
        options = self.zeroshot_data.get("options", [])
        for option in options:
            flow_dto_list.append(FlowDTO(name=option.get("class"), prompt=option.get("context")))

        prediction: str = classifier.predict(
            message=self.zeroshot_data.get("text"),
            flows=flow_dto_list,
            language=self.zeroshot_data.get("language")
        )

        formated_prediction = {
            "output": prediction
        }

        classification_formater = FormatClassification(formated_prediction)
        formatted_classification = classification_formater.get_classification(self.zeroshot_data)

        response = {"output": formatted_classification}
        return response

    def invoke(self):
        prompt = self._get_prompt(self.zeroshot_data)
        if settings.DEFAULT_CLASSIFICATION_MODEL != "zeroshot":
            return self._invoke_function_calling()
        invoke_zeroshot = self._invoke_zeroshot(self.model_backend)
        if invoke_zeroshot:
            return invoke_zeroshot(prompt)
        raise ValueError(f"Unsupported model backend: {self.model_backend}")
