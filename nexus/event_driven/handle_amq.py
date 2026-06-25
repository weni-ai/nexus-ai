"""
Consumer handlers for the Amazon MQ broker (weni-eda).

This handler is intentionally separate from the legacy
`nexus.projects.handle.handle_consumers` so the AMQ-only process started
by the `edaconsume-amq` entrypoint alias does not try to bind to queues that
only exist on the legacy RabbitMQ broker.

Only consumers that have been migrated to the new broker should be registered
here.
"""

from amqp.channel import Channel

from nexus.projects.consumers.project_consumer import WeniEDAProjectConsumer


def handle_amq_consumers(channel: Channel) -> None:
    channel.basic_consume("nexus-ai.projects", callback=WeniEDAProjectConsumer().handle)
