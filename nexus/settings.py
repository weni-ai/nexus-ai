"""
Django settings for nexus project.

Generated by 'django-admin startproject' using Django 4.2.6.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""
import os
from pathlib import Path

import environ

environ.Env.read_env(env_file=(environ.Path(__file__) - 2)(".env"))

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


env = environ.Env(
    SECRET_KEY=(str, "SK"),
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(lambda v: [s.strip() for s in v.split(",")], list("*")),
    CELERY_BROKER_URL=(str, "redis://localhost:6379/0"),
    WENIGPT_FLOWS_SEARCH_TOKEN=(str, ""),
    WENIGPT_FLOWS_CLASSIFY_TOKEN=(str, ""),
    AWS_S3_REGION_NAME=(str, ""),
    AWS_S3_BUCKET_NAME=(str, ""),
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
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "django_celery_results",
    "django_celery_beat",
    'rest_framework',
    'drf_yasg',
    # apps
    'nexus.users',
    'nexus.db',
    'nexus.orgs',
    'nexus.projects',
    'nexus.intelligences',
    'nexus.task_managers'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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

WENIGPT_FLOWS_CLASSIFY_TOKEN = env.str("WENIGPT_FLOWS_CLASSIFY_TOKEN")
WENIGPT_FLOWS_SEARCH_TOKEN = env.str("WENIGPT_FLOWS_SEARCH_TOKEN")

EXTERNAL_FLOWS_TOKENS = [
    WENIGPT_FLOWS_CLASSIFY_TOKEN,
    WENIGPT_FLOWS_SEARCH_TOKEN
]

AWS_S3_REGION_NAME = env.str("AWS_S3_REGION_NAME")
AWS_S3_BUCKET_NAME = env.str("AWS_S3_BUCKET_NAME")
