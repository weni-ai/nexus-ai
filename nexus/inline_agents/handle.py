from amqp.channel import Channel

from nexus.intelligences.consumers.conversation_consumer import ConversationConsumer


def handle_consumers(channel: Channel) -> None:
    channel.basic_consume("nexus.conversation", callback=ConversationConsumer().handle)