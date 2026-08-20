"""
Consumer handlers for the Amazon MQ broker (weni-eda).

This handler is intentionally separate from the legacy
`nexus.projects.handle.handle_consumers` so the AMQ-only process started
by the `edaconsume-amq` entrypoint alias does not try to bind to queues that
only exist on the legacy RabbitMQ broker.

Only consumers that have been migrated to the new broker should be registered
here.
"""

import logging

from django.conf import settings
from weni.eda.channels import Channel

from nexus.projects.consumers.project_consumer import WeniEDAProjectConsumer

logger = logging.getLogger(__name__)


def handle_amq_consumers(channel: Channel) -> None:
    # Project update events are still published only to the legacy RabbitMQ broker,
    # so WeniEDAProjectUpdateConsumer is not registered here yet.
    queue_name = settings.PROJECT_AMQ_QUEUE_NAME
    channel.basic_consume(
        queue_name,
        callback=WeniEDAProjectConsumer().handle,
    )
    logger.info(
        "[handle_amq_consumers] Registered WeniEDAProjectConsumer on queue %s",
        queue_name,
    )
