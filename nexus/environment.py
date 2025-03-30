import environ

environ.Env.read_env(env_file=(environ.Path(__file__) - 2)(".env"))

env = environ.Env(
    SECRET_KEY=(str, "SK"),
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(lambda v: [s.strip() for s in v.split(",")], list("*")),
    CELERY_BROKER_URL=(str, "redis://localhost:6379/0"),
    SENTENX_UPDATE_TASK_TOKEN=(str, ""),
    MODELS_SUPERUSER_TOKEN=(str, ""),
    RETAIL_SUPERUSER_TOKEN=(str, ""),
    APM_DISABLE_SEND=(bool, False),
    APM_SERVICE_DEBUG=(bool, False),
    APM_SERVICE_NAME=(str, ""),
    APM_SECRET_TOKEN=(str, ""),
    APM_SERVER_URL=(str, ""),
    FILTER_SENTRY_EVENTS=(list, []),
    CREDENTIAL_ENCRYPTION_KEY=(str, None),
)
