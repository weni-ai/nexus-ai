from amqp.channel import Channel

from .consumers.project_consumer import ProjectConsumer
from .consumers.trigger_consumer import TriggerConsumer


def handle_consumers(channel: Channel) -> None:
    channel.basic_consume("nexus-ai.projects", callback=ProjectConsumer().handle)
    channel.basic_consume("nexus-ai.triggers", callback=TriggerConsumer().handle)
