SECRET_KEY = "test"
DEBUG = True

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "router",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

USE_TZ = True

# Defaults used by router.entities.intelligences
DEFAULT_AGENT_NAME = "Agent"
DEFAULT_AGENT_ROLE = "Analyst"
DEFAULT_AGENT_PERSONALITY = "Friendly"
DEFAULT_AGENT_GOAL = "Help users"

ALLOWED_HOSTS = ["*"]
