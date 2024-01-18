from amqp.channel import Channel

from .consumers.org_consumer import OrgConsumer
from .consumers.org_auth_consumer import OrgAuthConsumer


def handle_consumers(channel: Channel) -> None:
    channel.basic_consume("nexus-ai.organizations", callback=OrgConsumer().handle)
    channel.basic_consume("nexus-ai.organization-authorization", callback=OrgAuthConsumer().handle)
