"""
Django settings for nexus project.

Generated by 'django-admin startproject' using Django 4.2.6.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""
import os
import sys
import sentry_sdk
from pathlib import Path

import environ

from sentry_sdk.integrations.django import DjangoIntegration


environ.Env.read_env(env_file=(environ.Path(__file__) - 2)(".env"))

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"


env = environ.Env(
    SECRET_KEY=(str, "SK"),
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(lambda v: [s.strip() for s in v.split(",")], list("*")),
    CELERY_BROKER_URL=(str, "redis://localhost:6379/0"),
    SENTENX_UPDATE_TASK_TOKEN=(str, ""),
    APM_DISABLE_SEND=(bool, False),
    APM_SERVICE_DEBUG=(bool, False),
    APM_SERVICE_NAME=(str, ""),
    APM_SECRET_TOKEN=(str, ""),
    APM_SERVER_URL=(str, ""),
)

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env.str("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool("DEBUG")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

AUTH_USER_MODEL = 'users.User'

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'mozilla_django_oidc',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "django_celery_results",
    "django_celery_beat",
    "django_prometheus",
    'rest_framework',
    'drf_yasg',
    'elasticapm.contrib.django',
    # apps
    'nexus.users',
    'nexus.db',
    'nexus.orgs',
    'nexus.projects',
    'nexus.intelligences',
    'nexus.task_managers',
    'nexus.event_driven',
    'nexus.actions',
    'corsheaders',
    'router',
    'nexus.logs',
]

MIDDLEWARE = [
    "elasticapm.contrib.django.middleware.TracingMiddleware",
    "elasticapm.contrib.django.middleware.Catch404Middleware",
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'nexus.logs.middleware.PrometheusAuthenticationMiddleware',
]

ROOT_URLCONF = 'nexus.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                "elasticapm.contrib.django.context_processors.rum_tracing",
            ],
        },
    },
]

WSGI_APPLICATION = 'nexus.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {"default": env.db(var="DEFAULT_DATABASE", default="sqlite:///db.sqlite3")}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

LANGUAGES = (
    ('en-us', 'English'),
    ('pt-br', 'Portuguese'),
    ('es', 'Spanish')
)

DEFAULT_LANGUAGE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = 'static/'

STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
# STORAGES = "whitenoise.storage.CompressedManifestStaticFilesStorage"
# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Celery config

REDIS_URL = env.str("CELERY_BROKER_URL", default="redis://localhost:6379/1")

CELERY_RESULT_BACKEND = "django-db"
CELERY_BROKER_URL = REDIS_URL
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_SERIALIZER = "json"

# Swagger

SWAGGER_SETTINGS = {
    "USE_SESSION_AUTH": False,
    "DOC_EXPANSION": "list",
    "APIS_SORTER": "alpha",
    "SECURITY_DEFINITIONS": {
        "OIDC": {"type": "apiKey", "name": "Authorization", "in": "header"}
    },
}

# WENIGPT

WENIGPT_FLOWS_CLASSIFY_TOKEN = env.str("WENIGPT_FLOWS_CLASSIFY_TOKEN")
WENIGPT_FLOWS_SEARCH_TOKEN = env.str("WENIGPT_FLOWS_SEARCH_TOKEN")
SENTENX_UPDATE_TASK_TOKEN = env.str("SENTENX_UPDATE_TASK_TOKEN")

EXTERNAL_SUPERUSERS_TOKENS = [
    WENIGPT_FLOWS_CLASSIFY_TOKEN,
    WENIGPT_FLOWS_SEARCH_TOKEN,
    SENTENX_UPDATE_TASK_TOKEN
]

# SENTENX

SENTENX_BASE_URL = env.str("SENTENX_BASE_URL")
SENTENX_AUTH_TOKEN = env.str("SENTENX_AUTH_TOKEN")
SENTENX_THRESHOLD = env.float("SENTENX_THRESHOLD", default=1.0)

# WENIGPT

WENIGPT_API_URL = env.str("WENIGPT_API_URL")
WENIGPT_SHARK_API_URL = env.str("WENIGPT_SHARK_API_URL")
WENIGPT_API_TOKEN = env.str("WENIGPT_API_TOKEN")
WENIGPT_COOKIE = env.str("WENIGPT_API_TOKEN")
WENIGPT_PROMPT_INTRODUCTION = env.str("WENIGPT_PROMPT_INTRODUCTION")
WENIGPT_PROMPT_TEXT = env.str("WENIGPT_PROMPT_TEXT")
WENIGPT_PROMPT_QUESTION = env.str("WENIGPT_PROMPT_QUESTION")
WENIGPT_PROMPT_REINFORCEMENT_INSTRUCTION = env.str("WENIGPT_PROMPT_REINFORCEMENT_INSTRUCTION")
WENIGPT_PROMPT_ANSWER = env.str("WENIGPT_PROMPT_ANSWER")
WENIGPT_MAX_NEW_TOKENS = env.str("WENIGPT_MAX_NEW_TOKENS")
WENIGPT_MAX_LENGHT = env.str("WENIGPT_MAX_LENGHT")
WENIGPT_TOP_P = env.str("WENIGPT_TOP_P")
WENIGPT_TOP_K = env.str("WENIGPT_TOP_K")
WENIGPT_TEMPERATURE = env.str("WENIGPT_TEMPERATURE")
WENIGPT_STOP = env.list("WENIGPT_STOP")
WENIGPT_VERSION = env.str("WENIGPT_VERSION")

WENIGPT_FINE_TUNNING_DEFAULT_VERSION = env.str("WENIGPT_FINE_TUNNING_DEFAULT_VERSION")
WENIGPT_FINE_TUNNING_VERSIONS = env.list("WENIGPT_FINE_TUNNING_VERSIONS")
WENIGPT_OPENAI_TOKEN = env.str("WENIGPT_OPENAI_TOKEN")

WENIGPT_FINE_TUNNING_MODELS = WENIGPT_FINE_TUNNING_VERSIONS.append(WENIGPT_FINE_TUNNING_DEFAULT_VERSION)

# AWS

AWS_S3_BUCKET_NAME = env.str("AWS_S3_BUCKET_NAME")
AWS_S3_REGION_NAME = env.str("AWS_S3_REGION_NAME")


FILE_UPLOAD_MAX_MEMORY_SIZE = 250 * 1024 * 1024

# Event Driven Architecture configurations

USE_EDA = env.bool("USE_EDA", default=False)

if USE_EDA:
    EDA_CONNECTION_BACKEND = "nexus.event_driven.connection.pymqp_connection.PyAMQPConnectionBackend"
    EDA_CONSUMERS_HANDLE = "nexus.event_driven.handle.handle_consumers"

    EDA_BROKER_HOST = env("EDA_BROKER_HOST", default="localhost")
    EDA_VIRTUAL_HOST = env("EDA_VIRTUAL_HOST", default="/")
    EDA_BROKER_PORT = env.int("EDA_BROKER_PORT", default=5672)
    EDA_BROKER_USER = env("EDA_BROKER_USER", default="guest")
    EDA_BROKER_PASSWORD = env("EDA_BROKER_PASSWORD", default="guest")
    EDA_WAIT_TIME_RETRY = env("EDA_WAIT_TIME_RETRY", default=5)

RABBITMQ_DEFAULT_USER = env.str("RABBITMQ_DEFAULT_USER")
RABBITMQ_DEFAULT_PASS = env.str("RABBITMQ_DEFAULT_PASS")

# OIDC

OIDC_RP_SERVER_URL = env.str("OIDC_RP_SERVER_URL")
OIDC_RP_REALM_NAME = env.str("OIDC_RP_REALM_NAME")
OIDC_OP_JWKS_ENDPOINT = env.str("OIDC_OP_JWKS_ENDPOINT")
OIDC_RP_CLIENT_ID = env.str("OIDC_RP_CLIENT_ID")
OIDC_RP_CLIENT_SECRET = env.str("OIDC_RP_CLIENT_SECRET")
OIDC_OP_AUTHORIZATION_ENDPOINT = env.str("OIDC_OP_AUTHORIZATION_ENDPOINT")
OIDC_OP_TOKEN_ENDPOINT = env.str("OIDC_OP_TOKEN_ENDPOINT")
OIDC_OP_USER_ENDPOINT = env.str("OIDC_OP_USER_ENDPOINT")
OIDC_DRF_AUTH_BACKEND = env.str(
    "OIDC_DRF_AUTH_BACKEND",
    default="nexus.authentication.authentication.WeniOIDCAuthenticationBackend",
)
OIDC_RP_SCOPES = env.str("OIDC_RP_SCOPES", default="openid email")


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "mozilla_django_oidc.contrib.drf.OIDCAuthentication"
    ],
}

if TESTING:
    REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"].append(
        "rest_framework.authentication.TokenAuthentication"
    )

CORS_ORIGIN_ALLOW_ALL = True

OPENAI_API_KEY = env.str("OPENAI_API_KEY")
CHATGPT_MODEL = env.str("CHATGPT_MODEL")
CHATGPT_ORGS = env.list("CHATGPT_ORGS")

CHATGPT_CONTEXT_PROMPT = env.str("CHATGPT_CONTEXT_PROMPT")
WENIGPT_CONTEXT_PROMPT = env.str("WENIGPT_CONTEXT_PROMPT")
WENIGPT_SHARK_CONTEXT_PROMPT = env.str("WENIGPT_SHARK_CONTEXT_PROMPT", WENIGPT_CONTEXT_PROMPT)

CHATGPT_NO_CONTEXT_PROMPT = env.str("CHATGPT_NO_CONTEXT_PROMPT")
WENIGPT_NO_CONTEXT_PROMPT = env.str("WENIGPT_NO_CONTEXT_PROMPT")
WENIGPT_SHARK_NO_CONTEXT_PROMPT = env.str("WENIGPT_SHARK_NO_CONTEXT_PROMPT", WENIGPT_NO_CONTEXT_PROMPT)

WENIGPT_DEFAULT_LANGUAGE = env.str("WENIGPT_DEFAULT_LANGUAGE", "por")

DJANGO_ALLOW_ASYNC_UNSAFE = env.bool("DJANGO_ALLOW_ASYNC_UNSAFE")
TRULENS_DATABASE_URL = env.str("TRULENS_DATABASE_URL", "sqlite:///default.sqlite")

FLOWS_REST_ENDPOINT = env.str("FLOWS_REST_ENDPOINT")

DEFAULT_AGENT_NAME = env.str("DEFAULT_AGENT_NAME")
DEFAULT_AGENT_ROLE = env.str("DEFAULT_AGENT_ROLE")
DEFAULT_AGENT_PERSONALITY = env.str("DEFAULT_AGENT_PERSONALITY")
DEFAULT_AGENT_GOAL = env.str("DEFAULT_AGENT_GOAL")
DEFAULT_INSTRUCTIONS = env.list("DEFAULT_INSTRUCTIONS")


LLM_CHAR_LIMIT = env.int("LLM_CHAR_LIMIT", default=640)
LLM_DEFAULT_CHAR_INSTRUCTION = env.str("LLM_DEFAULT_CHAR_INSTRUCTION")


FEW_SHOT_BOTO = env.str("FEW_SHOT_BOTO")
FEW_SHOT_CHATGPT = env.str("FEW_SHOT_BOTO")

TOKEN_LIMIT = env.int("TOKEN_LIMIT", default=0)

CHATGPT_POST_PROMPT = env.str("CHATGPT_POST_PROMPT")
WENIGPT_POST_PROMPT = env.str("WENIGPT_POST_PROMPT")

FLOWS_SEND_MESSAGE_INTERNAL_TOKEN = env.str("FLOWS_SEND_MESSAGE_INTERNAL_TOKEN")

# Sentry config

USE_SENTRY = env.bool("USE_SENTRY")

if USE_SENTRY:
    sentry_sdk.init(
        dsn=env.str("SENTRY_URL"),
        integrations=[DjangoIntegration()],
        environment=env.str("ENVIRONMENT"),
    )


# APM config

ELASTIC_APM = {
    "DISABLE_SEND": env.bool("APM_DISABLE_SEND"),
    "DEBUG": env.bool("APM_SERVICE_DEBUG"),
    "SERVICE_NAME": env.str("APM_SERVICE_NAME"),
    "SECRET_TOKEN": env.str("APM_SECRET_TOKEN"),
    "SERVER_URL": env.str("APM_SERVER_URL"),
    "ENVIRONMENT": env.str("ENVIRONMENT"),
    "DJANGO_TRANSACTION_NAME_FROM_ROUTE": True,
    "PROCESSORS": [
        "elasticapm.processors.sanitize_stacktrace_locals",
        "elasticapm.processors.sanitize_http_request_cookies",
        "elasticapm.processors.sanitize_http_headers",
        "elasticapm.processors.sanitize_http_wsgi_env",
        "elasticapm.processors.sanitize_http_request_body",
    ],
}

# TODO: temporary solution, undo later

IRC_UUID = env.str("IRC_UUID")
IRC_TOKEN = env.str("IRC_TOKEN")

WENIGPT_PAIRS_TEMPLATE_PROMPT = env.str("WENIGPT_PAIRS_TEMPLATE_PROMPT")
WENIGPT_SHARK_PAIRS_TEMPLATE_PROMPT = env.str("WENIGPT_PAIRS_TEMPLATE_PROMPT", WENIGPT_PAIRS_TEMPLATE_PROMPT)

WENIGPT_NEXT_QUESTION_TEMPLATE_PROMPT = env.str("WENIGPT_NEXT_QUESTION_TEMPLATE_PROMPT")
WENIGPT_SHARK_NEXT_QUESTION_TEMPLATE_PROMPT = env.str("WENIGPT_SHARK_NEXT_QUESTION_TEMPLATE_PROMPT", WENIGPT_NEXT_QUESTION_TEMPLATE_PROMPT)


WENIGPT_SHARK = "shark-1"
WENIGPT_GOLFINHO = "golfinho-1"

WENIGPT_DEFAULT_VERSION = env.str("WENIGPT_DEFAULT_VERSION", WENIGPT_GOLFINHO)

WENIGPT_VERSIONS = {
    WENIGPT_GOLFINHO : {
        "url": WENIGPT_API_URL,
        "context_prompt": WENIGPT_CONTEXT_PROMPT,
        "no_context_prompt": WENIGPT_NO_CONTEXT_PROMPT,
        "pairs_template_prompt": WENIGPT_PAIRS_TEMPLATE_PROMPT,
        "next_question_template_prompt": WENIGPT_NEXT_QUESTION_TEMPLATE_PROMPT,
    },
    WENIGPT_SHARK: {
        "url": WENIGPT_SHARK_API_URL,
        "context_prompt": WENIGPT_SHARK_CONTEXT_PROMPT,
        "no_context_prompt": WENIGPT_SHARK_NO_CONTEXT_PROMPT,
        "pairs_template_prompt": WENIGPT_SHARK_PAIRS_TEMPLATE_PROMPT,
        "next_question_template_prompt": WENIGPT_SHARK_NEXT_QUESTION_TEMPLATE_PROMPT,
    }
}

# Healthcheck external services:

HC_ZEROSHOT_URL = env.str("HC_ZEROSHOT_URL", "")
HC_GOLFINHO_URL = env.str("HC_GOLFINHO_URL", "")
HC_WENI_TOKEN = env.str("HC_WENI_TOKEN", "")
