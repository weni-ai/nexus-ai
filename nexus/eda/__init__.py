"""
Nexus adapters for weni-eda (phased consumer/producer migration).

Smoke test (``USE_EDA=True``, RabbitMQ running, queue ``nexus-ai.projects`` configured):

    poetry run python manage.py edaconsume

Publish a project-creation JSON payload to ``nexus-ai.projects`` and confirm the project
is created and logs show ``[ProjectConsumer] Project created``.
"""
