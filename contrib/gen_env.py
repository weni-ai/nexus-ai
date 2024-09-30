"""
Responsible for speeding up the generation of a local '.env' configuration file.
OBS: Run in development environment only
"""

import os

from django.core.management.utils import get_random_secret_key


def dict_to_config_string(data: dict) -> str:
    config_string = ""
    for key, value in data.items():
        config_string += f"{key}=\"{value}\"\n"

    return config_string.strip()


def generate_env():
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )

    if os.path.exists(env_path):
        print("A .env file already exists, delete it and run again")
        return

    VARIABLES = {
        "DEBUG": True,
        "ALLOWED_HOSTS": "*",
        "SECRET_KEY": get_random_secret_key(),
        "DEFAULT_DATABASE": "postgres://nexus:nexus@postgres:5432/nexus",
        "WENIGPT_FLOWS_CLASSIFY_TOKEN": "",
        "WENIGPT_FLOWS_SEARCH_TOKEN": "",
        "SENTENX_BASE_URL": "",
        "SENTENX_AUTH_TOKEN": "",
        "WENIGPT_API_URL": "",
        "WENIGPT_API_TOKEN": "",
        "WENIGPT_PROMPT_INTRODUCTION": "",
        "WENIGPT_PROMPT_TEXT": "",
        "WENIGPT_PROMPT_QUESTION": "",
        "WENIGPT_PROMPT_REINFORCEMENT_INSTRUCTION": "",
        "WENIGPT_PROMPT_ANSWER": "",
        "WENIGPT_MAX_NEW_TOKENS": "",
        "WENIGPT_MAX_LENGHT": "",
        "WENIGPT_TOP_P": "",
        "WENIGPT_TOP_K": "",
        "WENIGPT_TEMPERATURE": "",
        "WENIGPT_STOP": "",
        "WENIGPT_VERSION": "",
        "AWS_S3_BUCKET_NAME": "",
        "AWS_S3_REGION_NAME": "",
        "RABBITMQ_DEFAULT_USER": "",
        "RABBITMQ_DEFAULT_PASS": "",
        "OIDC_RP_SERVER_URL": "",
        "OIDC_RP_REALM_NAME": "",
        "OIDC_OP_JWKS_ENDPOINT": "",
        "OIDC_RP_CLIENT_ID": "",
        "OIDC_RP_CLIENT_SECRET": "",
        "OIDC_OP_AUTHORIZATION_ENDPOINT": "",
        "OIDC_OP_TOKEN_ENDPOINT": "",
        "OIDC_OP_USER_ENDPOINT": "",
        "OPENAI_API_KEY": "",
        "DJANGO_ALLOW_ASYNC_UNSAFE": False,
        "CHATGPT_ORGS": "",
        "CHATGPT_MODEL": "",
        "WENIGPT_FINE_TUNNING_DEFAULT_VERSION": "",
        "WENIGPT_FINE_TUNNING_VERSIONS": "",
        "WENIGPT_OPENAI_TOKEN": "",
        "DEFAULT_INSTRUCTIONS": "",
        "LLM_DEFAULT_CHAR_INSTRUCTION": "",
        "SENTRY_URL": "",
        "USE_SENTRY": False,
        "ENVIRONMENT": "",
        "FEW_SHOT_BOTO": "",
        "CHATGPT_POST_PROMPT": "",
        "WENIGPT_POST_PROMPT": "",
        "FLOWS_SEND_MESSAGE_INTERNAL_TOKEN": "",
        "CHATGPT_CONTEXT_PROMPT": "",
        "WENIGPT_CONTEXT_PROMPT": "",
        "CHATGPT_NO_CONTEXT_PROMPT": "",
        "WENIGPT_NO_CONTEXT_PROMPT": "",
        "FLOWS_REST_ENDPOINT": "",
        "DEFAULT_AGENT_NAME": "",
        "DEFAULT_AGENT_ROLE": "",
        "DEFAULT_AGENT_PERSONALITY": "",
        "DEFAULT_AGENT_GOAL": "",
        "USE_EDA": True,
        "USE_SENTRY": False,
        "SENTRY_URL": "",
        "IRC_UUID": "",
        "IRC_TOKEN": "",
        "WENIGPT_SHARK_API_URL": "SHARK",
        "WENIGPT_PAIRS_TEMPLATE_PROMPT": "",
        "WENIGPT_NEXT_QUESTION_TEMPLATE_PROMPT": "",
        "WENIGPT_TEST_API_URL": "TEST",
        "WENIGPT_TEST_CONTEXT_PROMPT": "TEST PROMPT",
        "WENIGPT_TEST_NO_CONTEXT_PROMPT": "TEST PROMPT WITHOUT CONTEXT",
        "WENIGPT_TEST_PAIRS_TEMPLATE_PROMPT": "TEST PAIRS",
        "WENIGPT_TEST_NEXT_QUESTION_TEMPLATE_PROMPT": "TEST QUESTION",
        "AWS_BEDROCK_DATASOURCE_ID": "",
        "AWS_BEDROCK_BUCKET_ARN": "",
        "AWS_BEDROCK_ACCESS_KEY": "",
        "AWS_BEDROCK_SECRET_KEY": "",
        "AWS_BEDROCK_REGION_NAME": "",
        "AWS_BEDROCK_KNOWLEDGE_BASE_ID": "",
        "AWS_BEDROCK_DATASOURCE_ID": "",
        "AWS_BEDROCK_BUCKET_NAME": "",
        "AWS_BEDROCK_EMBEDDING_MODEL_ARN": "",
        "AWS_BEDROCK_EMBEDDING_MODEL_DIMENSIONS": "",
        "AWS_BEDROCK_ROLE_ARN": "",
        "AWS_BEDROCK_MODEL_ID": "",
        "AWS_BEDROCK_ACCESS_KEY": "",
        "AWS_BEDROCK_SECRET_KEY": "",
        "USE_BEDROCK_WENIGPT": "",
        "ZEROSHOT_BASE_NLP_URL": "",
        "FLOWS_TOKEN_ZEROSHOT": "",
        "ZEROSHOT_SUFFIX": "",
        "ZEROSHOT_BEDROCK_AWS_KEY": "",
        "ZEROSHOT_BASE_NLP_URL": "",
        "ZEROSHOT_TOP_P": 0.1,
        "ZEROSHOT_TOP_K": 10,
        "ZEROSHOT_STOP": "",
        "ZEROSHOT_TEMPERATURE": 10,
        "ZEROSHOT_BEDROCK_MODEL_ID": "",
        "ZEROSHOT_N": 1,
        "ZEROSHOT_DO_SAMPLE": "",
        "ZEROSHOT_TOKEN": "",
        "ZEROSHOT_MAX_TOKENS": 20,
        "ZEROSHOT_MODEL_BACKEND": "",
        "ZEROSHOT_BEDROCK_AWS_SECRET": "",
        "ZEROSHOT_BEDROCK_AWS_REGION": "",
    }

    with open(env_path, "w") as configfile:
        configfile.write(dict_to_config_string(VARIABLES))


if __name__ == "__main__":
    generate_env()
