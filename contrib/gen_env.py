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
        "DATABASE_URL": "postgresql://nexus:nexus@localhost:5432/nexus",
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
        "DJANGO_ALLOW_ASYNC_UNSAFE": False
    }

    with open(env_path, "w") as configfile:
        configfile.write(dict_to_config_string(VARIABLES))


if __name__ == "__main__":
    generate_env()
